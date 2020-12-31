#!/usr/bin/env python
# -*-coding:utf-8 -*-
# ***************************************************************************
# 文件名称：run_hbase_monitor.py
# 功能描述：hive表数据稽核
# 输 入 表：
# 输 出 表：
# 创 建 者：hyn
# 创建日期：20201231
# 修改日志：
# 修改日期：
# ***************************************************************************
# 程序调用格式：nohup python /home/ocdp/hyn/hbase_monitor/run_hbase_monitor.py >> /home/ocdp/hyn/hbase_monitor/nuhup.out &
# ***************************************************************************

import os
import sys
import time
import hbase_monitor

# 启动
if __name__ == '__main__':

    while True:
        # 休息10分钟，600
        hbase_monitor.hbase_monitor()
        print 'sleep 1800s'

        time.sleep(1800)
