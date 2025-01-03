## Overview

**sqlog** is a library for hierarchical logging. All logs are grouped into sections, which simplifies reading and analysis.

---

## Quick Start

The library integrates with Python's standard logging module, providing its own log handler. Here's an example:

```python
import logging                  # Standard logging library
from datetime import datetime   # Work with date and time
from sqlog import SqFileHandler # Import sqlog log handler

# Initialize the log handler and specify the file to write to
sq_handler = SqFileHandler('log.sqlog')

logger = logging.getLogger('My Program')  # Create logger
logger.addHandler(sq_handler)             # Assign log handler

logging.basicConfig(level=logging.INFO)  # Set logging level to INFO

# Create a section and log within its context
with sq_handler.section('Program Work'):
    for i in range(10):
        # Create a subsection for each task
        with sq_handler.section(f'Task({i})') as sec:
            time_start = datetime.now()  # Task start time

            num = i ** 2  # Perform task
            logger.info(f'{i} ** 2 = {num}')  # Log result

            work_time = datetime.now() - time_start  # Task duration
            sec.add_header_str(f'work time: {work_time}')  # Add header to subsection
```

To convert logs into a readable format (e.g., HTML or Org files), use the following commands:

- Convert to Org file: `sqlog log.sqlog -o log.org`
- Convert to HTML file: `sqlog log.sqlog -o log.html`

---

## Using the Library

### Library Operation Description

When initializing the log handler (`SqFileHandler`), a main section (`top_section`) is created. This section serves as the root and contains all subsequent sections and logs. Each program run creates a new main section, which serves as the root for all logs of the current program execution, logically dividing them into sections.

Logs are divided into sections, making them structured and easier to analyze. Subsections further organize logs depending on the developer's needs. Logs are written to the current section: initially, this is the main section. When entering the context of a subsection, it becomes the current section. After exiting the context, the parent section becomes the current one again.

Sections are created using the `section` method of the handler (`SqFileHandler`), which automatically manages their hierarchy. Independent sections can also be created for manual log management. Here’s an example:

```python
# Create an independent section
common_section = sq_handler.section('Common')

# Log in the current and independent sections
with sq_handler.section('Task'):
    logger.info('Task status ...', common_section)
```

You can also create subsections for independent sections:

```python
with sq_handler.section('Task'):
    common_subsection = common_section.section('Common Subsection')
    logger.info('Task state ...', common_subsection)
```

Thus, logs are written both in the current section and the specified independent section, offering flexibility in organizing entries.

Important: All sections must belong to the same file and be created by the same handler. Logging in sections of different files will not work.

Log files have the `.sqlog` extension and are implemented in SQLite3 database format. These files collect all logs, which can later be converted into readable formats.

### Section Header Formatting

Section headers support formatting using a subset of HTML.

*Available tags:*
- `<b>` Bold text
- `<i>` Italic
- `<u>` Underlined text
- `<s>` Strikethrough text
- `<pre>` or `<code>` Code block
- `<d>` or `<delim>` Delimiter (single tag)

Tag attributes (only for HTML output format):
- `color`: Text color
- `bg` or `background`: Background color of the text

To create a section with an unformatted header: `.section('some text...', html=False)`  
Or to add unformatted text to the header: `.add_header_str('some text...', html=False)`

---

## Conversion to Readable Format

### Utility Arguments

The `sqlog` utility accepts the following arguments:
- Positional argument: Path to `.sqlog` file
- `-o` or `--output`: Path to the output file
- `-f` or `--format`: Output format (HTML or Org)
- `-l` or `--log_format`: Log format string, default:
  - For Org format: `- %(levelname)s :: %(name)s :: %(message)s`
  - For HTML format: `<b>%(levelname)s</b> <span class="delimiter">|</span> %(name)s <span class="delimiter">|</span> %(message)s`
  - More details: [Python Logging Docs](https://docs.python.org/3/library/logging.html#logrecord-attributes)
- `-s` or `--start_level`: Starting section level for Org format (default: 1)

If `--output` is not specified, the result is printed in the terminal (requires explicit format specification). The format is automatically determined by the output file extension.

---

## Example

```python
import asyncio                   # Import async library
import logging                   # Import standard logging module
from random import randint       # Import function to generate random numbers
from datetime import datetime    # Import date and time module
from sqlog import SqFileHandler  # Import log handler from sqlog library

# Create a logger to be used for logging
logger = logging.getLogger('My Program')
# Create SqFileHandler to write logs to file log.sqlog
sq_handler = SqFileHandler('log.sqlog')
# Create a section for logs to be written to the 'Common' section
common_section = sq_handler.section('Common')
# Add sq_handler to our logger
logger.addHandler(sq_handler)

# Set logging level to DEBUG to record all messages
logger.setLevel(logging.DEBUG)
# Disable propagation of logs so they don’t get written to other handlers
logger.propagate = False

# Async function to perform tasks with delays
async def task(i):
    # Simulate random delay
    await asyncio.sleep(randint(0, 3))
    
    # Create a subsection for each task with a unique name
    with sq_handler.section(f'<b>Task({i})</b>') as sec:
        # Record task start time
        time_start = datetime.now()

        # Simulate delay as if the task is running
        await asyncio.sleep(randint(0, 3))

        # Perform computation (square a number)
        num = i ** 2

        # Log the result in the current section and 'Common' section
        logger.info(f'{i} ** 2 = {num}', common_section)

        # Another delay before task completion
        await asyncio.sleep(randint(0, 3))

        # Calculate task duration
        work_time = datetime.now() - time_start

        # Add task duration info to subsection header
        sec.add_header_str(f'<delim>work time: {work_time}')

# Main async function to run all tasks
async def main():
    # Record the start time of all tasks
    start_dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Create the main section with start time
    with sq_handler.section(f'<b>Start</b> {start_dt}'):
        # Run all 10 tasks concurrently
        await asyncio.gather(*[task(i) for i in range(10)])

# Get the current event loop for async execution
loop = asyncio.get_event_loop_policy().get_event_loop()
# Run the main loop until all
```
