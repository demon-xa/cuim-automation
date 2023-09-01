#!/bin/bash

# Check caller.py
if pgrep -x "caller.py" > /dev/null
then
    # process run. and we exit
    echo "Process run. wait"
    exit 0
else
    # Process not run. Can start
    python3 /var/www/html/srv/scripts/caller.py
fi