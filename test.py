import logging
from pathlib import Path
from random import randint
from datetime import datetime

from sqlog import SqFileHandler

# Logging
logger = logging.getLogger("test")

logdir = Path("log")
logdir.mkdir(exist_ok=True)

sq_handler = SqFileHandler(logdir.joinpath("log.sqlog"))
common_section = sq_handler.section("Common")
logger.addHandler(sq_handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False

other_handler = SqFileHandler(logdir.joinpath("other.sqlog"))
other_section = other_handler.section("Other")

logging.basicConfig(level=logging.INFO)

start_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with sq_handler.section(f'<b color="red">Start</b> {start_dt}', html=False):
    for i in range(10):
        with sq_handler.section(f'<b color="green">Task({i})</b>') as sec:
            time_start = datetime.now()

            num = i**2
            logger.info(f"{i} ** 2 = {num}", common_section, None, other_section)

            work_time = datetime.now() - time_start
            sec.add_header_str(
                f'<delim color="black" bg="yellow"> work time: {work_time}'
            )
