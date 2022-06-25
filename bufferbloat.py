#!/usr/bin/python
"CS244 Spring 2022 Assignment 1: Bufferbloat on Mininet"

from mininet.topo import Topo
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.log import lg, info
from mininet.util import dumpNodeConnections
from mininet.cli import CLI
from mininet.clean import cleanup

from subprocess import Popen, PIPE
from time import sleep, time
from multiprocessing import Process
from argparse import ArgumentParser

from monitor import monitor_qlen
import termcolor as T

import numpy

import sys
import os
import math

# TODO: Don't just read the TODO sections in this code.  Remember that
# one of the goals of this assignment is for you to learn how to use
# Mininet. :-)

parser = ArgumentParser(description="Bufferbloat tests")
parser.add_argument('--bw-host', '-B',
                    type=float,
                    help="Bandwidth of host links (Mb/s)",
                    default=1000)

parser.add_argument('--bw-net', '-b',
                    type=float,
                    help="Bandwidth of bottleneck (network) link (Mb/s)",
                    required=True)

parser.add_argument('--delay',
                    type=float,
                    help="Link propagation delay (ms)",
                    required=True)

parser.add_argument('--dir', '-d',
                    help="Directory to store outputs",
                    required=True)

parser.add_argument('--time', '-t',
                    help="Duration (sec) to run the experiment",
                    type=int,
                    default=10)

parser.add_argument('--maxq',
                    type=int,
                    help="Max buffer size of network interface in packets",
                    default=100)

# Linux uses CUBIC-TCP by default that doesn't have the usual sawtooth
# behaviour.  For those who are curious, invoke this script with
# --cong cubic and see what happens...
# sysctl -a | grep cong should list some interesting parameters.
parser.add_argument('--cong',
                    help="Congestion control algorithm to use",
                    default="reno")

# Expt parameters
args = parser.parse_args()

class BBTopo(Topo):
    "Simple topology for bufferbloat experiment."

    def build(self, n=2):
        # Here are two hosts
        hosts = []
        for i in range(1,n+1):
            hosts.append(self.addHost('h%d'%(i)))

        # Here I have created a switch.  If you change its name, its
        # interface names will change from s0-eth1 to newname-eth1.
        switch = self.addSwitch('s0')

        # TODO: Add links with appropriate characteristics
        self.addLink(hosts[0], switch, bw=args.bw_host, delay=args.delay, max_queue_size=args.maxq)
        self.addLink(hosts[1], switch, bw=args.bw_net, delay=args.delay, max_queue_size=args.maxq)

# Simple wrappers around monitoring utilities.  You are welcome to
# contribute neatly written (using classes) monitoring scripts for
# Mininet!

# tcp_probe is a kernel module which records cwnd over time. In linux >= 4.16
# it has been replaced by the tcp:tcp_probe kernel tracepoint.
def start_tcpprobe(outfile="cwnd.txt"):
    os.system("rmmod tcp_probe; modprobe tcp_probe full=1;")
    Popen("cat /proc/net/tcpprobe > %s/%s" % (args.dir, outfile),
          shell=True)

def stop_tcpprobe():
    Popen("killall -9 cat", shell=True).wait()

def start_qmon(iface, interval_sec=0.1, outfile="q.txt"):
    monitor = Process(target=monitor_qlen, args=(iface, interval_sec, outfile))
    monitor.start()
    return monitor

# iperf 参数
# -c/s：客户端模式/服务端模式
# -w：设置缓冲区大小
# -t：设置测试的时长，单位为秒，不设置默认10s
# -l：指定包大小，TCP默认8k，UDP默认1470字节
def start_iperf(net):
    h1 = net.get('h1')
    h2 = net.get('h2')
    print("Starting iperf server...")
    # For those who are curious about the -w 16m parameter, it ensures
    # that the TCP flow is not receiver window limited.  If it is,
    # there is a chance that the router buffer may not get filled up.
    h2.popen("iperf -s -w 16m") # server
    # TODO: Start the iperf client on h1.  Ensure that you create a
    # long lived TCP flow. You may need to redirect iperf's stdout to avoid blocking.
    h1.popen("iperf -c %s -t %d > %s/iperf_client.txt" % (h2.IP(), args.time, args.dir)) # client

def start_webserver(net):
    print("Starting webserver...")
    h1 = net.get('h1')
    proc = h1.popen("python2 http/webserver.py", shell=True) # 这里一定要使用 python2
    sleep(1)
    return [proc]

def page_fatcher(net):
    print("Fetching webpages")
    
    h1 = net.getNodeByName('h1')
    h2 = net.getNodeByName('h2')
    fetch_times = []
    start_time = time()

    while True:                                              
        print("%.1fs left..." % (args.time - (time() - start_time)))

        fetch = h2.popen("curl -o /dev/null -s -w %{} {}/index.html".format("{time_total}", h1.IP()))
        fetch.wait()
        fetch_times.append(float(fetch.communicate()[0]))

        sleep(1.6)

        fetch = h2.popen("curl -o /dev/null -s -w %{} {}/index.html".format("{time_total}", h1.IP()))
        fetch.wait()
        fetch_times.append(float(fetch.communicate()[0]))

        sleep(1.6)

        fetch = h2.popen("curl -o /dev/null -s -w %{} {}/index.html".format("{time_total}", h1.IP()))
        fetch.wait()
        fetch_times.append(float(fetch.communicate()[0]))

        if (args.time - (time() - start_time)) <= 0:
            break

        sleep((args.time - (time() - start_time)) % 5) # 等待本轮的5秒钟结束

        if (args.time - (time() - start_time)) <= 0:
            break

    return fetch_times

def start_ping(net):
    # TODO: Start a ping train from h1 to h2 (or h2 to h1, does it
    # matter?)  Measure RTTs every 0.1 second.  Read the ping man page
    # to see how to do this.

    # Hint: Use host.popen(cmd, shell=True).  If you pass shell=True
    # to popen, you can redirect cmd's output using shell syntax.
    # i.e. ping ... > /path/to/ping.txt
    # Note that if the command prints out a lot of text to stdout, it will block
    # until stdout is read. You can avoid this by runnning popen.communicate() or
    # redirecting stdout
    h1 = net.get('h1')
    h2 = net.get('h2')

    h1.popen("ping -i 0.1 %s > %s/ping.txt"%(h2.IP(), args.dir), shell=True)

def bufferbloat():
    if not os.path.exists(args.dir):
        os.makedirs(args.dir)
    os.system("sysctl -w net.ipv4.tcp_congestion_control=%s" % args.cong)

    # Cleanup any leftovers from previous mininet runs
    cleanup()

    topo = BBTopo()
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    # This dumps the topology and how nodes are interconnected through
    # links.
    dumpNodeConnections(net.hosts)
    # This performs a basic all pairs ping test.
    net.pingAll() #简单测试网络是否配置成功

    # Start all the monitoring processes
    start_tcpprobe("cwnd.txt") # 通过 tcp_probe 探测 cwnd 的变化情况
    start_ping(net)            # 以 0.1 秒为间隔 ping

    # TODO: Start monitoring the queue sizes.  Since the switch I
    # created is "s0", I monitor one of the interfaces.  Which
    # interface?  The interface numbering starts with 1 and increases.
    # Depending on the order you add links to your network, this
    # number may be 1 or 2.  Ensure you use the correct number.
    qmon = start_qmon(iface='s0-eth2', outfile='%s/q.txt' % (args.dir)) # 监控队列长度，这里添加了两个链路，所以是eth2

    # TODO: Start iperf, webservers, etc.
    start_webserver(net) # 启动 web 服务器
    start_iperf(net) # 使用 iperf 从 h1 向 h2 发送数据

    # Hint: The command below invokes a CLI which you can use to
    # debug.  It allows you to run arbitrary commands inside your
    # emulated hosts h1 and h2.
    #
    # CLI(net)

    # TODO: measure the time it takes to complete webpage transfer
    # from h1 to h2 (say) 3 times every 5 seconds. Hint: check what the following
    # command does: curl -o /dev/null -s -w %{time_total} google.com
    # Now use the curl command to fetch webpage from the webserver you
    # spawned on host h1 (not from google!)
    # Hint: have a separate function to do this and you may find the
    # loop below useful.    print "Fetching webpages"
    fetch_times = page_fatcher(net)

    # TODO: compute average (and standard deviation) of the fetch
    # times.  You don't need to plot them.  Just note it in your
    # README and explain.
    print("Average of fetch time: %f\n" % numpy.average(fetch_times))
    print("Standard deviation of fetch times: %f\n" % numpy.std(fetch_times))


    stop_tcpprobe()
    if qmon is not None:
        qmon.terminate()
    net.stop()
    # Ensure that all processes you create within Mininet are killed.
    # Sometimes they require manual killing.
    Popen("pgrep -f webserver.py | xargs kill -9", shell=True).wait()

if __name__ == "__main__":
    bufferbloat()
