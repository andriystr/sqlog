import asyncio
import logging
from pathlib import Path
from random import randint
from datetime import datetime

from sqlog import SqFileHandler

# Logging
logger = logging.getLogger("async-test")

logdir = Path("alog")
logdir.mkdir(exist_ok=True)

sq_handler = SqFileHandler(logdir.joinpath("log.sqlog"))
common_section = sq_handler.section("Common")
logger.addHandler(sq_handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False

logging.basicConfig(level=logging.INFO)


async def task(i):
    await asyncio.sleep(randint(0, 3))
    with sq_handler.section(f"<b>Task({i})</b>") as sec:
        time_start = datetime.now()

        await asyncio.sleep(randint(0, 3))
        num = i**2
        logger.info(f"{i} ** 2 = {num}", common_section)

        await asyncio.sleep(randint(0, 3))
        work_time = datetime.now() - time_start
        sec.add_header_str(f"<delim>work time: {work_time}")


async def main():
    start_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sq_handler.section(f"<b>Start</b> {start_dt}"):
        await asyncio.gather(*[task(i) for i in range(10)])


loop = asyncio.get_event_loop_policy().get_event_loop()
loop.run_until_complete(main())
