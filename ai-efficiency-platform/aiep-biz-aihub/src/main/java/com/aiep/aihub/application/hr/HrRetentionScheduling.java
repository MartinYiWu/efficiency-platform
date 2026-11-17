package com.aiep.aihub.application.hr;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/** 到期撤销与删除补偿必须在进程重启后继续从数据库调度。 */
@Configuration
@EnableScheduling
public class HrRetentionScheduling {}
