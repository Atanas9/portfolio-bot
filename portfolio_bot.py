import os
import json
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import yfinance as yf
from io import StringIO
import csv
import pandas as pd
import requests

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Store portfolio data
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

# Timezone for Italy
italy_tz = pytz.timezone('Europe/Rome')

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    daily_briefing.start()

def parse_csv_data(csv_text):
    """Parse CSV data and extract holdings"""
    try:
        f = StringIO(csv_text)
        reader = csv.DictReader(f)
        data = {}
        for row in reader:
            ticker = row.get('Ticker', '').strip()
            shares = float(row.get('Shares', 0))
            if ticker and shares > 0:
                data[ticker] = shares
        return data
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        return {}

def get_price(ticker):
    """Fetch current price from Yahoo Finance"""
    try:
        data = yf.Ticker(ticker)
        price = data.info.get('currentPrice') or data.history(period='1d')['Close'].iloc[-1]
        return float(price)
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return None

def calculate_portfolio_value():
    """Calculate current portfolio value and weights"""
    if not portfolio_data:
        return None, None
    
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
    
    # Calculate current weights
    current_weights = {}
    for ticker, data in portfolio_values.items():
        current_weights[ticker] = data['value'] / total_value if total_value > 0 else 0
    
    return portfolio_values, current_weights, total_value

def get_rebalancing_needs(portfolio_values, current_weights, total_value):
    """Calculate what needs to be bought/sold to match target weights"""
    rebalancing = {}
    
    for ticker, target_weight in target_weights.items():
        current_weight = current_weights.get(ticker, 0)
        weight_diff = target_weight - current_weight
        euro_amount = weight_diff * total_value
        
        if ticker in portfolio_values:
            current_value = portfolio_values[ticker]['value']
            current_shares = portfolio_values[ticker]['shares']
        else:
            current_value = 0
            current_shares = 0
        
        target_value = target_weight * total_value
        
        rebalancing[ticker] = {
            'current_value': current_value,
            'target_value': target_value,
            'difference': euro_amount,
            'current_weight': current_weight * 100,
            'target_weight': target_weight * 100,
            'action': 'BUY' if euro_amount > 1 else 'SELL' if euro_amount < -1 else 'HOLD'
        }
    
    return rebalancing

def get_news_summary(ticker):
    """Fetch news for a ticker using NewsAPI (free tier)"""
    try:
        # Using a free news API
        url = f"https://api.bing.com/news/search?q={ticker}&count=3"
        # Note: This is a simplified version. For production, use NewsAPI with key
        return f"News for {ticker}: Check your browser for latest news"
    except:
        return f"Could not fetch news for {ticker}"

@bot.command(name='portfolio')
async def portfolio_command(ctx):
    """Show current portfolio holdings"""
    portfolio_values, current_weights, total_value = calculate_portfolio_value()
    
    if not portfolio_values:
        await ctx.send("❌ No portfolio data loaded. Use `/load-csv` first.")
        return
    
    embed = discord.Embed(
        title="📊 Portfolio Overview",
        description=f"Total Value: €{total_value:,.2f}",
        color=discord.Color.blue()
    )
    
    for ticker, data in sorted(portfolio_values.items()):
        weight = current_weights.get(ticker, 0) * 100
        embed.add_field(
            name=f"{ticker}",
            value=f"Shares: {data['shares']:.2f}\nPrice: €{data['price']:.2f}\nValue: €{data['value']:,.2f}\nWeight: {weight:.1f}%",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='rebalance')
async def rebalance_command(ctx):
    """Show rebalancing recommendations"""
    portfolio_values, current_weights, total_value = calculate_portfolio_value()
    
    if not portfolio_values:
        await ctx.send("❌ No portfolio data loaded.")
        return
    
    rebalancing = get_rebalancing_needs(portfolio_values, current_weights, total_value)
    
    embed = discord.Embed(
        title="⚖️ Rebalancing Recommendations",
        color=discord.Color.green()
    )
    
    for ticker, rec in sorted(rebalancing.items()):
        action = rec['action']
        diff = rec['difference']
        color_emoji = "🔴" if diff < 0 else "🟢" if diff > 0 else "⚪"
        
        embed.add_field(
            name=f"{color_emoji} {ticker}",
            value=f"Current: {rec['current_weight']:.1f}% | Target: {rec['target_weight']:.1f}%\nAction: {action} €{abs(diff):,.2f}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='add-cash')
async def add_cash_command(ctx, amount: float):
    """Suggest allocation for new money"""
    portfolio_values, current_weights, total_value = calculate_portfolio_value()
    
    if not portfolio_values:
        await ctx.send("❌ No portfolio data loaded.")
        return
    
    new_total = total_value + amount
    embed = discord.Embed(
        title=f"💰 Allocation for €{amount:,.2f} New Cash",
        color=discord.Color.gold()
    )
    
    for ticker, target_weight in sorted(target_weights.items()):
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

@bot.command(name='news')
async def news_command(ctx, ticker: str = None):
    """Get latest news on holdings"""
    if ticker:
        news = get_news_summary(ticker.upper())
        await ctx.send(f"📰 **{ticker.upper()}**: {news}")
    else:
        embed = discord.Embed(
            title="📰 Portfolio News",
            description="Use `/news TICKER` to get news on a specific holding",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

@bot.command(name='load-csv')
async def load_csv_command(ctx):
    """Load portfolio data from CSV"""
    await ctx.send("📥 Please paste your Trading 212 CSV data (format: Ticker, Shares):")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=300)
        global portfolio_data
        portfolio_data = parse_csv_data(msg.content)
        await ctx.send(f"✅ Loaded {len(portfolio_data)} holdings!")
    except:
        await ctx.send("❌ Timeout or error. Please try again.")

@tasks.loop(minutes=1)
async def daily_briefing():
    """Send daily briefing at 8 AM Italian time"""
    now = datetime.now(italy_tz)
    
    if now.hour == 8 and now.minute == 0:
        # Find the channel (first text channel in the server)
        channel = None
        for guild in bot.guilds:
            for ch in guild.text_channels:
                channel = ch
                break
        
        if channel:
            portfolio_values, current_weights, total_value = calculate_portfolio_value()
            
            if portfolio_values:
                rebalancing = get_rebalancing_needs(portfolio_values, current_weights, total_value)
                
                embed = discord.Embed(
                    title="📊 Morning Portfolio Briefing",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Total Value",
                    value=f"€{total_value:,.2f}",
                    inline=False
                )
                
                # Rebalancing needs
                needs_rebalance = any(r['action'] != 'HOLD' for r in rebalancing.values())
                if needs_rebalance:
                    embed.add_field(
                        name="⚠️ Rebalancing Needed",
                        value="Check `/rebalance` for details",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="✅ Portfolio Balanced",
                        value="All weights are on target!",
                        inline=False
                    )
                
                await channel.send(embed=embed)

@daily_briefing.before_loop
async def before_daily_briefing():
    await bot.wait_until_ready()

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))
