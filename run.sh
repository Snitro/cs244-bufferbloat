#!/bin/bash
set -e

# Note: Mininet must be run as root.  So invoke this shell script
# using sudo.

time=60
bwnet=10
# TODO: If you want the RTT to be 4ms what should the delay on each
# link be?  Set this value correctly.
delay=2

iperf_port=5001

# make sure we don't use a cached cwnd
sysctl -w net.ipv4.tcp_no_metrics_save=1
# make sure the local socket buffers don't become the bottleneck
sysctl -w "net.ipv4.tcp_mem=10240 87380 268435456"

for qsize in 20 100; do
    dir=bb-q$qsize

    mn -c > /dev/null 2>&1

    python3 bufferbloat.py --dir=$dir --time=$time --bw-net=$bwnet --delay=$delay --maxq=$qsize

    # TODO: Ensure the input file names match the ones you use in
    # bufferbloat.py script.  Also ensure the plot file names match
    # the required naming convsention when submitting your tarball.
    python2 plot_tcpprobe.py -f $dir/cwnd.txt -o $dir/cwnd-iperf.png -p $iperf_port
    python2 plot_queue.py -f $dir/q.txt -o $dir/q.png
    python2 plot_ping.py -f $dir/ping.txt -o $dir/rtt.png
done

echo "Simulations are done! Results can be retrieved via the server"
python -m SimpleHTTPServer
