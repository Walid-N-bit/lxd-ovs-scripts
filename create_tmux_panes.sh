#!/bin/bash
# create_tmux_panes.sh

# small function to visualize progress
dots() {
    local step="$1"
    local str="."
    for i in $(seq 1 $((step))); do
        str="$str."
    done
    echo $str
}

# grab env variables
read -s -p "Password: " PW
echo
export PW

# list of commands environment variable: CMD
# example: export CMD="<command-1>,<command-2>"
# commands should be a string split by ","
CMD=$*
IFS=, read -r -a CMD_LIST <<< "$CMD"
export CMD_LIST

# # number of panes environment variable: P_NUM
# P_NUM=$((P_NUM - 1))
# export P_NUM

# automatically get the number of panes from the number of commands
P_NUM=${#CMD_LIST[@]}
((P_NUM--))

# create tmux session and panes
tmux new-session -d -s sesh
for i in $(seq 1 $P_NUM); do
    # echo "$i"
    tmux split-pane -v
done
tmux select-layout even-vertical

# send keys to panes
pane=0
# echo "counter=$pane"
for cmd in "${CMD_LIST[@]}"; do
    # echo "pane = $pane"
    # echo "command: $cmd"
    dots $pane
    tmux select-pane -t sesh:0.$pane
    tmux send-keys "expect worker_proc.exp '$cmd'" enter
    ((pane++))
    sleep 3
done

# unset CMD
# unset P_NUM