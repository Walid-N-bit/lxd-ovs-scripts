#!/bin/bash

### get server
server=$(lxc list -f csv -c n | grep '^cont-.*0$')
# echo $server

### edit pyproject.toml

lxc exec $server -- nano fl_app/pyproject.toml

