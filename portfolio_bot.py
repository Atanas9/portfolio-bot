import os
import sys
os.environ['DISCORD_PY_DISABLE_VOICE'] = '1'

import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import yfinance as yf

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

portfolio_data = {}
target_weights = {
    'VOO': 0.50,
    'EUNL.DE': 0.10,
    'IAPD.DE': 0.07,
    'JPIE.L': 0.03,
    'SGLN.L': 0.10,
    'DBXP.DE': 0.08,
    'XEC1.DE': 0.02,
    'JPM': 0.02,
    'SPCX': 0.02,
    'KO': 0.02,
    'NVDA': 0.02,
    'LLY': 0.02,
}

italy_tz = pytz.timezone('Europe/Rome')

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    try:
        daily_briefing.start()
    except:
        pass

def parse_csv_data(csv_text):
    lines = csv_text.strip().split('\n')
    data = {}
    start_idx = 0
    if lines and ('Ticker' in lines[0] or 'ticker' in lines[0].lower()):
        start_idx = 1
    
    for line in lines[start_idx:]:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 2:
            ticker = parts[0].strip()
            try:
                shares = float(parts[1])
                if ticker and shares > 0:
                    data[ticker] = shares
            except:
                pass
    
    return data

def get_price(ticker):
    try:
        tick = yf.Ticker(ticker)
        hist = tick.history(period='1d')
        if len(hist) > 0:
            price = hist['Close'].iloc[-1]
            return float(price)
        return None
    except:
        return None

def calculate_portfolio_value():
    if not portfolio_data:
        return {}, {}, 0
    
    portfolio_values = {}
    total_value = 0
    
    for ticker, shares in portfolio_data.items():
        price = get_price(ticker)
        if price:
            value = shares * price
            portfolio_values[ticker] = {
                'shares': shares,
                'price': price,
                'value': value
            }
            total_value += value
    
    current_weights = {}
    for ticker, data in portfolio_values.items():
        current_weights[ticker] = data['value'] / total_value if total_value > 0 else 0
    
    return portfolio_values, current_weights, total_value

def get_rebalancing_needs(portfolio_values, current_weights, total_value):
    rebalancing = {}
    
    for ticker, target_weight in target_weights.items():
        current_weight = current_weights.get(ticker, 0)
        weight_diff = target_weight - current_weight
        euro_amount = weight_diff * total_value
        
        rebalancing[ticker] = {
            'current_value': portfolio_values.get(ticker, {}).get('value', 0),
            'target_value': target_weight * total_value,
            'difference': euro_amount,
            'current_weight': current_weight * 100,
            'target_weight': target_weight * 100,
            'action': 'BUY' if euro_amount > 1 else 'SELL' if euro_amount < -1 else 'HOLD'
        }
    
    return rebalancing

@bot.command(name='portfolio')
async def portfolio_command(ctx):
    portfolio_values, current_weights, total_value = calculate_portfolio_value()
    
    if not portfolio_values:
        await ctx.send("❌ No portfolio data loaded. Use `/load-csv` first.")
        return
    
    embed = discord.Embed(
        title="📊 Portfolio Overview",
        description=f"Total Value: €{total_value:,.2f}",
        color=discord.Color.blue()
    )
    
    for ticker in sorted(portfolio_values.keys()):
        data = portfolio_values[ticker]
        weight = current_weights.get(ticker, 0) * 100
        embed.add_field(
            name=f"{ticker}",
            value=f"Shares: {data['shares']:.2f}\nPrice: €{data['price']:.2f}\nValue: €{data['value']:,.2f}\nWeight: {weight:.1f}%",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='rebalance')
async def rebalance_command(ctx):
    portfolio_values, current_weights, total_value = calculate_portfolio_value()
    
    if not portfolio_values:
        await ctx.send("❌ No portfolio data loaded.")
        return
    
    rebalancing = get_rebalancing_needs(portfolio_values, current_weights, total_value)
    
    embed = discord.Embed(
        title="⚖️ Rebalancing Recommendations",
        color=discord.Color.green()
    )
    
    for ticker in sorted(rebalancing.keys()):
        rec = rebalancing[ticker]
        diff = rec['difference']
        color_emoji = "🔴" if diff < -0.01 else "🟢" if diff > 0.01 else "⚪"
        
        embed.add_field(
            name=f"{color_emoji} {ticker}",
            value=f"Current: {rec['current_weight']:.1f}% | Target: {rec['target_weight']:.1f}%\nAction: {rec['action']} €{abs(diff):,.2f}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='add-cash')
async def add_cash_command(ctx, amount: float):
    portfolio_values, current_weights, total_value = calculate_portfolio_value()
    
    if not portfolio_values:
        await ctx.send("❌ No portfolio data loaded.")
        return
    
    embed = discord.Embed(
        title=f"💰 Allocation for €{amount:,.2f} New Cash",
        color=discord.Color.gold()
    )
    
    for ticker in sorted(target_weights.keys()):
        target_weight = target_weights[ticker]
        allocation = target_weight * amount
        current_price = get_price(ticker)
        if current_price:
            shares_to_buy = allocation / current_price
            embed.add_field(
                name=ticker,
                value=f"Allocate: €{allocation:,.2f}\nBuy: {shares_to_buy:.4f} shares at €{current_price:.2f}",
                inline=False
            )
    
    await ctx.send(embed=embed)

@bot.command(name='load-csv')
async def load_csv_command(ctx):
    await ctx.send("📥 Please paste your Trading 212 CSV data in the next message.\n\nFormat:\n```\nTicker,Shares\nVOO,50\nEUNL.DE,20\n```")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=300)
        global portfolio_data
        portfolio_data = parse_csv_data(msg.content)
        if portfolio_data:
            await ctx.send(f"✅ Loaded {len(portfolio_data)} holdings!")
        else:
            await ctx.send("❌ Could not parse CSV.")
    except:
        await ctx.send("❌ Timeout.")

@tasks.loop(minutes=1)
async def daily_briefing():
    try:
        now = datetime.now(italy_tz)
        
        if now.hour == 8 and now.minute == 0:
            channel = None
            for guild in bot.guilds:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        channel = ch
                        break
            
            if channel and portfolio_data:
                portfolio_values, current_weights, total_value = calculate_portfolio_value()
                
                if portfolio_values:
                    rebalancing = get_rebalancing_needs(portfolio_values, current_weights, total_value)
                    
                    embed = discord.Embed(
                        title="📊 Morning Portfolio Briefing",
                        description=f"Date: {now.strftime('%Y-%m-%d')}",
                        color=discord.Color.blue()
                    )
                    
                    embed.add_field(
                        name="💰 Total Value",
                        value=f"€{total_value:,.2f}",
                        inline=False
                    )
                    
                    needs_rebalance = any(r['action'] != 'HOLD' for r in rebalancing.values())
                    if needs_rebalance:
                        rebalance_count = sum(1 for r in rebalancing.values() if r['action'] != 'HOLD')
                        embed.add_field(
                            name="⚠️ Rebalancing Needed",
                            value=f"{rebalance_count} positions need adjustment.",
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="✅ Portfolio Balanced",
                            value="All weights are on target!",
                            inline=False
                        )
                    
                    await channel.send(embed=embed)
    except Exception as e:
        print(f"Error in briefing: {e}")

@daily_briefing.before_loop
async def before_daily_briefing():
    await bot.wait_until_ready()

token = os.getenv('DISCORD_TOKEN')
if token:
    bot.run(token)
else:
    print("ERROR: DISCORD_TOKEN not set!")
