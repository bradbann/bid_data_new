#!/usr/bin/env python
# -*-coding:utf-8 -*-
# ***************************************************************************
# 文件名称：copy_data_sy_ocdp_partition_table_v2_config.py
# 功能描述：迁移分区表
# 输 入 表：
# 输 出 表：
# 创 建 者：hyn
# 创建日期：20200815
# 修改日志：
# 修改日期：
# ***************************************************************************
# 参数说明：1.分区类型（全量，日分区），2.批次号，3.top300（0：不是，1：是）
# 程序调用格式：# python copy_data_sy_ocdp_partition_table_v2_config.py 1 1000 0
# ***************************************************************************

import os
import sys
from datetime import datetime
import datetime as date_time
import conn_db
import config


# 对分区表、非分区表分类
# 功能结构
# 读取表名
# 处理日期输入数据
# 构造迁移语句
# 执行迁移语句
# 分区表直接拷贝文件夹
# 打印日志

class CopyData():

    # 参数初始化
    def __init__(self, input_batch):
        self.input_batch = input_batch
        self.bandwidth = '10'
        self.map_num = '10'
        self.all = 'all'

    # 获取任务，mysql获取表名，每次获取一个列表进行遍历
    def read_table_name(self):

        while True:

            # 获取配置参数，带宽，map数
            get_config_sql = "select network,map from tb_copy_data_config where migration_batch='" + input_batch + "' limit 1"
            get_config_result = conn_db.select(get_config_sql)
            self.bandwidth = get_config_result[0][0]
            self.map_num = get_config_result[0][1]

            print '获取配置参数', get_config_result, self.bandwidth, self.map_num

            # 获取可以稽核表名列表，表里获取分区键
            get_task_sql = "select id, table_name ,partition_type,partition_time from tb_tmp_copy_get_partition_task where copy_status='0' and   migration_batch='" + input_batch + "' order by partition_time asc limit 10"

            print '获取配置参数sql：', get_config_sql
            print '获取任务sql：', get_task_sql

            select_result = conn_db.select(get_task_sql)
            print '获取任务：', select_result

            # 取不到任务
            if not select_result:
                print '无迁移任务'
                exit(0)

            # 遍历集合，更新此批次状态,status=1
            update_sql = "update tb_tmp_copy_get_partition_task  set copy_status='1'"
            in_condition = ''
            for i in select_result:
                in_condition = str(i[0]) + "," + in_condition

            update_sql = update_sql + "where id in (" + in_condition + "0)"

            print '更新此批次状态', update_sql

            # 测试
            result = conn_db.insert(update_sql)

            # 遍历表名，插日志
            for i in select_result:
                table_name = i[1]
                partition_type = i[2]
                partition_time = i[3]

                # 当前时间
                now_time = str(date_time.datetime.now())[0:19]

                insert_sql = "insert into tb_tmp_copy_data_log (data_source,table_name,partition_type,partition_time,copy_status,chk_status,start_time,end_time) values('%s','%s','%s','%s','%s','%s','%s','%s')" % (
                    config.data_source, table_name, partition_type, partition_time, config.copy_status_1,
                    config.chk_status_0, now_time, '')

                result = conn_db.insert(insert_sql)

                # todo，检测数据量是否为0，为0，return直接跳过，
                if not self.ssh_check_sy_data(table_name, partition_type, partition_time):
                    print '# 忽略迁移'
                    continue

                print '### 开始迁移'

                # 删除分区，添加分区,todo
                self.add_partition(table_name, partition_type, partition_time)

                # 拷贝数据
                self.copy_data(table_name, partition_type, partition_time)

    # 检测数据量是否为0，为0，return直接跳过，不为0继续同步
    def ssh_check_sy_data(self, table_name, partition_type, partition_time):

        check_sh = config.sy_ssh_sh + "select count(%s) from %s where %s='%s' ; \' \" > /home/ocdp/hyn/copy_hdfs_data/copy_data_sy_count/table_count/%s_%s.txt " % (
            partition_type, table_name, partition_type, partition_time, table_name, partition_time)

        print 'check_sh:', check_sh
        result = os.system(check_sh)
        f = open('/home/ocdp/hyn/copy_hdfs_data/copy_data_sy_count/table_count/%s_%s.txt' % (table_name, partition_time), 'r')
        table_info = f.readlines()
        f.close()
        # table_info = open('./table_count/%s_%s.txt' % (table_name, partition_time), 'r').readlines()

        print '### table_info', table_info

        # 判断是否为空
        if len(table_info) == 0:
            # 不存在
            print 'sy库不存在'

            update_sql = "update tb_tmp_copy_data_log set result_not_exist='no' where table_name='%s' and partition_time='%s'" % (
                table_name, partition_time)
            conn_db.insert(update_sql)
            return False
        else:
            table_count = int(table_info[0].replace('\n', ''))
            if table_count > 0:
                print '#sy库有数据', table_count
                update_sql = "update tb_tmp_copy_data_log set sy_count='%s',result_not_exist='%s' where table_name='%s' and partition_time='%s'" % (
                    table_count, table_count, table_name, partition_time)
                conn_db.insert(update_sql)
                return True
            else:
                # 老库为0，是否更新到mysql
                print 'sy库数量为0'

                update_sql = "update tb_tmp_copy_data_log set result_not_exist='0' where table_name='%s' and partition_time='%s'" % (
                    table_name, partition_time)
                conn_db.insert(update_sql)

                return False

    # 添加分区，清理数据，优化之后不需要添加分区
    def add_partition(self, table_name, partition_type, partition_date):
        # 重建分区
        delete_partition_sql = "alter table " + table_name + " drop if  exists partition (" + partition_type + "=" + partition_date + ");"
        delete_partition_sql_sh = config.excute_hive_sh + delete_partition_sql + "\'"

        # 先测试单周期
        add_partition_sql = "alter table " + table_name + " add if not exists partition (" + partition_type + "=" + partition_date + ");"

        print add_partition_sql

        add_partition_sql_sh = config.excute_hive_sh + add_partition_sql + "\'"

        print '分区已添加：', delete_partition_sql_sh, add_partition_sql_sh
        os.popen(delete_partition_sql_sh)
        os.popen(add_partition_sql_sh  )

    # 构造迁移语句
    def copy_data(self, table_name, partition_type, partition_date):

        print '迁移过程参数', self.bandwidth, self.map_num

        # 记录开始迁移时间172.19.168.100
        st_time = date_time.datetime.now()
        print "[info]" + str(st_time), ":表数据迁移开始:", table_name, "分区:", partition_date

        # hadoop distcp -i hdfs://192.168.190.89:8020/apps/hive/warehouse/csap.db/tb_si_cu_voma_limit_whitelist_day/statis_date=20170617 hdfs://172.19.168.4:8020/warehouse/tablespace/managed/hive/tb_si_cu_voma_limit_whitelist_day

        distcp_sh = "hadoop distcp -bandwidth " + self.bandwidth + " -m  " + self.map_num + " -pb -i hdfs://192.168.190.88:8020/apps/hive/warehouse/csap.db/" + table_name + "/" + partition_type + "=" + partition_date + " /warehouse/tablespace/managed/hive/csap.db/" + table_name + "/"
        # distcp_sh = "hadoop distcp -bandwidth " + self.bandwidth + " -m  " + self.map_num + " -pb -i hdfs://192.168.190.89:8020/apps/hive/warehouse/csap.db/" + table_name + "/* hdfs://172.19.168.4:8020/warehouse/tablespace/managed/hive/csap.db/" + table_name + "/"

        result = os.system(distcp_sh)

        print '#迁移命令:', distcp_sh

        print '###################'

        print '##### 迁移信息', result, type(result)

        print '###################'

        end_time = date_time.datetime.now()

        # 同步失败，更新数据库
        if result != 0:
            update_status_sql = "update tb_tmp_copy_data_log set remark1='" + str(
                result) + "', copy_status ='" + config.copy_status_3 + "',start_time='" + str(
                st_time)[
                                                                                          0:19] + "',end_time='" + str(
                end_time)[0:19] + "' where table_name='" + table_name + "' and partition_time='" + partition_date + "\'"

            print '更新sql:', update_status_sql

            conn_db.insert(update_status_sql)

            return
        else:

            print "[info]" + str(end_time), ":表数据迁移结束:", table_name, "分区:", partition_date
            print '共耗时:', end_time - st_time, 'S'

            self.copy_ok(table_name, partition_date, st_time, end_time)

    # 数据迁移完成更新数据库记录
    def copy_ok(self, table_name, partition_date, st_time, end_time):
        update_status_sql = "update tb_tmp_copy_data_log set copy_status ='" + config.copy_status_2 + "',start_time='" + str(
            st_time)[
                                                                                                                     0:19] + "',end_time='" + str(
            end_time)[0:19] + "' where table_name='" + table_name + "' and partition_time='" + partition_date + "\'"

        print '更新sql:', update_status_sql

        conn_db.insert(update_status_sql)

        # 修复表，停止修复表
        # self.repair_table(table_name)

        # 收集统计信息
        self.add_info(table_name, partition_date)

        # print '数据迁移同步,更新同步状态完成:', table_name, partition_date
        # if str(date_time.datetime.now())[11:13] == '06':
        #     print '到达早上6点,自动停止迁移任务,当前时间:', str(date_time.datetime.now())[0:19]
        #     exit(0)

    # 修复表
    def repair_table(self, table_name):
        repair_table_sql = "msck repair table " + table_name

        add_partition_sql_sh = config.excute_hive_sh + repair_table_sql + "\'"

        os.popen(add_partition_sql_sh)
        # 修复表

    # 收集表统计信息
    def add_info(self, table_name, partition_date):
        add_info_sql = "ANALYZE TABLE " + table_name + " partition(" + config.partition_statis_date + "= " + partition_date + " ) COMPUTE STATISTICS;"

        add_info_sql_sh = config.excute_hive_sh + add_info_sql + "\'"

        print '收集元数据库统计信息:', add_info_sql_sh

        os.popen(add_info_sql_sh)

        print '[info] ', str(date_time.datetime.now())[0:19], ':收集元数据库统计信息完成：', table_name, '分区：', partition_date


# 全量表
# python copy_data_sy_to_ocdp.py 1 0 20 30

# 启动
if __name__ == '__main__':

    input_length = len(sys.argv)
    print 'input_str: ', len(sys.argv)

    if input_length == 2:

        # 批次号，分批处理ss
        input_batch = sys.argv[1]

        copy_data_object = CopyData(input_batch)
        copy_data_object.read_table_name()

    else:
        print '输入参数有误'
