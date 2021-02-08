from binance_balancer import real_iteratey
from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler()
scheduler.add_job(real_iteratey, 'interval', minutes=20)
scheduler.start()