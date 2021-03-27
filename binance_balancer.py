'''
Binance Balancer
2020 - Sandy Bay

Re-balances every hour based on manually fixed allocations
Defaults to limit orders which are cancelled if unfilled and recalculated for the new rebalance

'''
import math
import time
import pandas as pd
import numpy as np
from binance.client import Client
from csv import writer
from datetime import datetime
import pprint
from dotenv import load_dotenv
import os
import telebot

load_dotenv()

# set keys
api_key = os.getenv("api_key")
api_secret = os.getenv("api_secret")

# set weights
# look for 6 to 12 month value
# hedge fiat (usd,rub,try,eur)
# focus on trusted cryptos with the following priority
# security
# value
# usage
# fees
# privacy
# speed

lastweights = {
    "SUSHI":0.015,
    "SOL":0.015,
    "FIL":0.022,
    "ATOM":0.020,
    "THETA":0.025,
    "IOTA":0.025,
    "AAVE":0.028,
    "DOGE":0.030,
    "VET":0.030,
    "XTZ":0.032,
    "TRX":0.036,
    "XRP":0.036,
    "XEM":0.036,
    "UNI":0.044,
    "XLM":0.036,
    "BCH":0.054,
    "LINK":0.060,
    "BNB":0.060,
    "ADA":0.076,
    "DOT":0.065,
    "LTC":0.065,
    "ETH": 0.08,
    "BTC": 0.11,
    "FTT":0.0,
    "XMR":0.00,
    "USDT":0.000
    }

# Timestamped bitcoin and usd portfolio value
csvBalance = 'binance_balance_log.csv'

# globals
prices = {} # asset prices in btc
prices['BTC'] = 1.0
BTCUSD = 0.0
balances = {}
balancesbtc = {}
totalbtc = 0
diffs = {}
steps = {}
ticks = {}
minQtys = {}
threshold = 0.00018
transaced = False
percentage = {}
percentageThreadhold = 0.003

# connect
client = Client(api_key, api_secret)
# time offset binance bug fix
# servTime = client.get_server_time()
# time_offset  = servTime['serverTime'] - int(time.time() * 1000)

def send(msg, chat_id=os.getenv("telegram_chat_id"), token=os.getenv("telegram_api")):
    # """
    # Send a message to a telegram user or group specified on chatId
    # chat_id must be a number!
    # """
    try:
        bot = telebot.TeleBot(token, parse_mode=None) # You can set parse_mode by default. HTML or MARKDOWN
        bot.send_message(chat_id=chat_id, text=msg)
    except Exception:
        pass


def sanityCheck():
    sane = False
    sumWeights = round(sum(lastweights.values()),4)
    if sumWeights == 1.0000:
        sane = True
    else:
        print("Incorrect weights. Sum ratios must equal 1.0. Currently ",sumWeights)
    return sane

def append_list_as_row(file_name, list_of_elem):
    # Open file in append mode
    with open(file_name, 'a+', newline='') as write_obj:
        # Create a writer object from csv module
        csv_writer = writer(write_obj)
        # Add contents of list as last row in the csv file
        csv_writer.writerow(list_of_elem)

def saveBalance():
    if transaced:
        send(str(totalbtc)+" "+str(totalbtc * BTCUSD))
    # Returns a datetime object containing the local date and time
    # dateTimeObj = datetime.now()
    # List of row elements (Timestamp, Bitcoin balance, USD balance, Notes)
    # row_contents = [str(dateTimeObj), str(totalbtc) , str(totalbtc * BTCUSD)]
    # Append a list as new line to an old csv file
    # append_list_as_row(csvBalance, row_contents)


def getPrices():
    global prices, BTCUSD
    # get prices
    priceinfo = client.get_all_tickers()
    for price in priceinfo:
        sym = price['symbol']
        asset = sym[0:-3]
        quote = sym[-3:]
        p = float(price['price'])
        if sym == 'BTCUSDT':
            BTCUSD = p
            prices['USDT'] = 1 / p
        elif quote == 'BTC':
            if asset in lastweights:
                prices[asset] = p
    # print('Prices (BTC)')
    # pprint.pprint(prices)

def getBalance():
    global balances, balancesbtc, totalbtc
    totalbtc = 0
    # get balance
    info = client.get_account()
    for balance in info['balances']:
        free = float( balance['free'] )
        locked =  float( balance['locked'] )
        asset = balance['asset']
        if asset in lastweights:
            bal = free + locked
            balances[ asset ] = bal
            balancesbtc[ asset ] = bal * prices[asset]
            totalbtc = totalbtc + bal * prices[asset]
    # print(balances)
    print("Balances (BTC)")
    # pprint.pprint(balancesbtc)
    print("Total (BTC / USD)")
    print(totalbtc," BTC /  $ ",totalbtc*BTCUSD)

def getDiffs():
    global diffs
    global percentage
    # get difference
    for asset in lastweights:
        adjshare = totalbtc * lastweights[asset]
        currshare = balancesbtc[asset]
        diff = adjshare - currshare
        diffs [ asset ] = diff
        percentage [ asset ] = round((currshare / totalbtc) - lastweights [asset], 4)
    diffs = dict(sorted(diffs.items(), key=lambda x: x[1]))
    percentage = dict(sorted(percentage.items(), key=lambda x: x[1]))
    print('Adjustments (BTC)')
    # pprint.pprint(printDiffs)
    pprint.pprint(percentage)

def cancelOrders():
    # cancel current orders
    print('Canceling open orders')
    orders = client.get_open_orders()
    for order in orders:
        sym = order['symbol']
        asset = sym[0:-3]
        if sym == 'BTCUSDT' or asset in lastweights:
            orderid = order['orderId']
            try:
                result = client.cancel_order(symbol=sym,orderId=orderid)
            except:
                pass
            # print(result)

def step_size_to_precision(ss):
    return ss.find('1') - 1

def format_value(val, step_size_str):
    precision = step_size_to_precision(step_size_str)
    if precision > 0:
        return "{:0.0{}f}".format(val, precision)
    return math.floor(int(val))

def getSteps():
    global steps, ticks, minQtys
    # step sizes
    info = client.get_exchange_info()
    for dat in info['symbols']:
        sym = dat['symbol']
        asset = dat['baseAsset']
        quote = dat['quoteAsset']
        filters = dat['filters']
        if quote == 'BTC' and asset in lastweights:
            for filt in filters:
                if filt['filterType'] == 'LOT_SIZE':
                    steps[asset] = filt['stepSize']
                elif filt['filterType'] == 'PRICE_FILTER':
                    ticks[asset] = filt['tickSize']
                elif filt['filterType'] == 'MIN_NOTIONAL':
                    minQtys[asset] = filt['minNotional']
        elif sym == 'BTCUSDT':
            for filt in filters:
                if filt['filterType'] == 'LOT_SIZE':
                    steps[sym] = filt['stepSize']
                elif filt['filterType'] == 'PRICE_FILTER':
                    ticks[sym] = filt['tickSize']
                elif filt['filterType'] == 'MIN_NOTIONAL':
                    minQtys['USDT'] = filt['minNotional']


def simOrders():
    # all go through btc
    # this can be smart routed later
    global diffs
    getSteps()

    # set sell orders
    for asset in diffs:
        diff = diffs[asset]
        if asset != 'BTC':
            thresh = float(minQtys[asset])
            if  diff <  -threshold : # threshold $ 1
                if asset != 'BTC' and asset != 'USDT':
                    sym = asset + 'BTC'
                    amountf = 0-diff # amount in btc

                    amount = format_value ( amountf / prices[asset] , steps[asset] )
                    price = format_value ( prices [ asset ] + 0.003 * prices [ asset ], ticks[asset] )# adjust for fee
                    minNotion = float(amount) * float(price)
                    if minNotion > thresh:
                        diffs[asset] = diffs[asset] + amountf
                        diffs['BTC'] = diffs['BTC'] - amountf
                        print('Setting sell order for {}, amount:{}, price:{}, thresh:{}'.format(asset,amount,price,threshold))

                elif asset == 'USDT':
                    sym = 'BTCUSDT'
                    amount = 0-diff
                    if amount > ( thresh / BTCUSD ):
                        diffs[asset] = diffs[asset] + amount
                        diffs['BTC'] = diffs['BTC'] - amount
                        amount = format_value ( amount  , steps[sym] )
                        price = format_value ( BTCUSD - 0.003 * BTCUSD , ticks[sym])# adjust for fee
                        print('Setting buy order for {}, amount:{}, price:{}'.format('BTC',amount,price))

    # set buy orders
    diffs = dict(sorted(diffs.items(), key=lambda x: x[1], reverse=True))

    for asset in diffs:
        diff = diffs[ asset ]
        if asset != 'BTC':
            thresh = float( minQtys[ asset ] )
            if  diff >  threshold : # threshold $ 1
                if asset != 'BTC' and asset != 'USDT':
                    sym = asset + 'BTC'
                    amountf = diff

                    amount = format_value ( amountf / prices[asset] , steps[asset] )
                    price = format_value ( prices [ asset ] - 0.003 * prices [ asset ] , ticks[asset] )# adjust for fee
                    minNotion = float(amount) * float(price)
                    if minNotion > thresh:
                        diffs[asset] = diffs[asset] - amountf
                        diffs['BTC'] = diffs['BTC'] + amountf
                        print('Setting buy order for {}, amount:{}, price:{}, thresh:{}'.format(asset,amount,price,threshold))

                elif asset == 'USDT':
                    sym = 'BTCUSDT'
                    amount = diff
                    if amount > ( thresh / BTCUSD ):
                        diffs[asset] = diffs[asset] - amount
                        diffs['BTC'] = diffs['BTC'] + amount
                        amount = format_value ( amount  , steps[sym] )
                        price = format_value ( BTCUSD + 0.003 * BTCUSD , ticks[sym])# adjust for fee
                        print('Setting sell order for {}, amount:{}, price:{}'.format('BTC',amount,price))


    # print ( 'Final differences' )
    # pprint.pprint ( diffs )

def placeOrders(market):
    # all go through btc
    # this can be smart routed later
    global diffs
    global transaced
    transaced = False
    getSteps()
    # set sell orders
    for asset in diffs:
        diff = diffs[asset]
        if asset != 'BTC':
            thresh = float(minQtys[asset])
            if  diff <  -threshold : # threshold $ 1
                if asset != 'BTC' and asset != 'USDT':
                    sym = asset + 'BTC'
                    amountf = 0-diff # amount in btc

                    amount = format_value ( amountf / prices[asset] , steps[asset] )
                    price = format_value ( prices [ asset ] + 0.003 * prices [ asset ], ticks[asset] )# adjust for fee
                    minNotion = float(amount) * float(price)
                    if minNotion > thresh:
                        transaced = True
                        diffs[asset] = diffs[asset] + amountf
                        diffs['BTC'] = diffs['BTC'] - amountf
                        if market:
                            message = 'Setting MARKET sell order for {}, amount:{}, price:{}'.format(asset,amount,price)
                            print(message)
                            send(message)
                            order = client.order_market_sell(
                                symbol = sym,
                                quantity = amount )
                        else:
                            message = 'Setting sell order for {}, amount:{}, price:{}, thresh:{}'.format(asset,amount,price,threshold)
                            print(message)
                            send(message)
                            order = client.order_limit_sell(
                                symbol = sym,
                                quantity = amount,
                                price = price )

                elif asset == 'USDT':
                    sym = 'BTCUSDT'
                    amount = 0-diff
                    if amount > ( thresh / BTCUSD ):
                        diffs[asset] = diffs[asset] + amount
                        diffs['BTC'] = diffs['BTC'] - amount
                        amount = format_value ( amount  , steps[sym] )
                        price = format_value ( BTCUSD - 0.003 * BTCUSD , ticks[sym])# adjust for fee
                        if market:
                            message = 'Setting MARKET buy order for {}, amount:{}, price:{}'.format('BTC',amount,price)
                            print(message)
                            send(message)
                            order = client.order_market_buy(
                                symbol = sym,
                                quantity = amount )
                        else:
                            message = 'Setting buy order for {}, amount:{}, price:{}'.format('BTC',amount,price)
                            print(message)
                            send(message)
                            order = client.order_limit_buy(
                                symbol = sym,
                                quantity = amount,
                                price = price )



    # set buy orders
    diffs = dict(sorted(diffs.items(), key=lambda x: x[1], reverse=True))

    for asset in diffs:
        diff = diffs[ asset ]
        if asset != 'BTC':
            thresh = float( minQtys[ asset ] )
            if  diff >  threshold : # threshold $ 1
                if asset != 'BTC' and asset != 'USDT':
                    sym = asset + 'BTC'
                    amountf = diff

                    amount = format_value ( amountf / prices[asset] , steps[asset] )
                    price = format_value ( prices [ asset ] - 0.003 * prices [ asset ] , ticks[asset] )# adjust for fee
                    minNotion = float(amount) * float(price)
                    if minNotion > thresh:
                        transaced = True
                        diffs[asset] = diffs[asset] - amountf
                        diffs['BTC'] = diffs['BTC'] + amountf
                        if market:
                            message = 'Setting MARKET buy order for {}, amount:{}, price:{}'.format(asset,amount,price)
                            print(message)
                            send(message)
                            order = client.order_market_buy(
                                symbol = sym,
                                quantity = amount )
                        else:
                            message = 'Setting buy order for {}, amount:{}, price:{}, thresh:{}'.format(asset,amount,price,threshold)
                            print(message)
                            send(message)
                            order = client.order_limit_buy(
                                symbol = sym,
                                quantity = amount,
                                price = price )

                elif asset == 'USDT':
                    sym = 'BTCUSDT'
                    amount = diff
                    if amount > ( thresh / BTCUSD ):
                        diffs[asset] = diffs[asset] - amount
                        diffs['BTC'] = diffs['BTC'] + amount
                        amount = format_value ( amount  , steps[sym] )
                        price = format_value ( BTCUSD + 0.003 * BTCUSD , ticks[sym])# adjust for fee
                        if market:
                            message = 'Setting MARKET sell order for {}, amount:{}, price:{}'.format('BTC',amount,price)
                            print(message)
                            send(message)
                            order = client.order_market_sell(
                                symbol = sym,
                                quantity = amount )
                        else:
                            message = 'Setting sell order for {}, amount:{}, price:{}'.format('BTC',amount,price)
                            print(message)
                            send(message)
                            order = client.order_limit_sell(
                                symbol = sym,
                                quantity = amount,
                                price = price )


    # print ( 'Final differences' )
    # pprint.pprint ( diffs )

def iteratey():
    sane = sanityCheck()
    if sane == True:
        getPrices()
        getBalance()
        getDiffs()
        simOrders()

        var = input("Enter Y/market to confirm trading: ")
        if var == "Y" or var == "market":
            getPrices()
            getBalance()
            getDiffs()
            cancelOrders()
            placeOrders(var == "market")
            saveBalance()

def real_iteratey():
    global transaced
    transaced = False
    getPrices()
    getBalance()
    getDiffs()
    cancelOrders()
    placeOrders(False)
    saveBalance()
