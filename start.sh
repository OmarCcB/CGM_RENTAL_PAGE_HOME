#!/bin/bash
screen -dmS cgmrental bash -c '
cd /var/www/cgmrental
source venv/bin/activate
gunicorn -w 4 -b 0.0.0.0:8015 app:app
exec bash
'
