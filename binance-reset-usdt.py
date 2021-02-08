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
from apscheduler.schedulers.blocking import BlockingScheduler
from csv import writer
from datetime import datetime
import pprint
from dotenv import load_dotenv
import os
import traceback

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
    "USDT":1.0
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

# connect
client = Client(api_key, api_secret)
# time offset binance bug fix
# servTime = client.get_server_time()
# time_offset  = servTime['serverTime'] - int(time.time() * 1000)

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
    # Returns a datetime object containing the local date and time
    dateTimeObj = datetime.now()
    # List of row elements (Timestamp, Bitcoin balance, USD balance, Notes)
    row_contents = [str(dateTimeObj), str(totalbtc) , str(totalbtc * BTCUSD)]
    # Append a list as new line to an old csv file
    append_list_as_row(csvBalance, row_contents)

def getBalance():
    global balances, balancesbtc, totalbtc 
    totalbtc = 0
    # get balance
    info = client.get_account()
    for balance in info['balances']:
        free = float( balance['free'] ) 
        locked =  float( balance['locked'] )
        asset = balance['asset']
        bal = free + locked
        if bal > 0.0:
            balances[ asset ] = bal
    print(balances)
    print("Balances (BTC)")
    # pprint.pprint(info)
    print("Total (BTC / USD)")
    print(totalbtc," BTC /  $ ",totalbtc*BTCUSD)

def cancelOrders():
    # cancel current orders
    print('Canceling open orders')
    orders = client.get_open_orders()
    for order in orders:
        sym = order['symbol']
        asset = sym[0:-3]
        if sym == 'BTCUSDT' or asset in lastweights:
            orderid = order['orderId']
            result = client.cancel_order(symbol=sym,orderId=orderid)
            # print(result)

def simOrders():
    # all go through usdt
    global balances
    # set sell orders
    for asset in balances:
        if asset != 'BTC':
            continue
        balance = balances[asset]
        if asset != 'USDT':
            print('Setting sell order for {}, amount:{}'.format(asset,balance))

def placeOrders():
    # all go through usdt
    global balances
    # set sell orders
    for asset in balances:
        balance = "{:0.0{}f}".format(balances[asset] * 0.95, 6)
        if asset != 'USDT':
            try:
                order = client.order_market_sell(
                                symbol = asset+'USDT',
                                quantity = balance
                                )
            except Exception as error:
                print("Sell: " + asset)
                traceback.print_exc()

        

def iteratey():
    sane = sanityCheck()
    if sane == True:
        getBalance()
        simOrders()

        var = input("Enter Y to confirm trading: ")
        if var == "Y":
            getBalance()
            cancelOrders()
            placeOrders()
            saveBalance()

iteratey()
# scheduler = BlockingScheduler()
# scheduler.add_job(iteratey, 'interval', minutes=20)
# scheduler.start()
