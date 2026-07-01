"""守护进程启动脚本"""

if __name__ == "__main__":
    # Windows 上 multiprocessing 需要 freeze_support
    import multiprocessing
    multiprocessing.freeze_support()

    # 初始化 TaskManager
    from mos.core.task import get_task_manager
    manager = get_task_manager()

    # 重新加载插件任务
    from mos.core.plugin import get_registry
    plugin_registry = get_registry()
    for plugin_def in plugin_registry.all():
        if plugin_def.register_tasks:
            plugin_def.register_tasks(manager.registry, manager.event_bus)

    # 启动调度器
    manager.scheduler.start()

    # 保持运行
    import time
    from mos.core.logging import get_logger
    logger = get_logger("daemon")
    logger.info("守护进程已启动")

    while True:
        time.sleep(60)
