import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class SyncMonitor:
    """数据同步监控与运维报告生成"""

    def __init__(self):
        self.task_records = []

    def add_record(self, task_name: str, status: str, detail: dict = None):
        """记录任务执行状态"""
        record = {
            "task_name": task_name,
            "status": status,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "detail": detail or {}
        }
        self.task_records.append(record)

        if status == "success":
            logger.info(f"任务【{task_name}】执行成功")
        elif status == "failed":
            logger.error(f"任务【{task_name}】执行失败")
        else:
            logger.info(f"任务【{task_name}】状态：{status}")

    def generate_report(self, output_file: str = None) -> dict:
        """生成标准化运维报告"""
        success_count = sum(1 for r in self.task_records if r["status"] == "success")
        failed_count = sum(1 for r in self.task_records if r["status"] == "failed")
        total_count = len(self.task_records)
        success_rate = success_count / total_count * 100 if total_count > 0 else 0

        report = {
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_tasks": total_count,
            "success_tasks": success_count,
            "failed_tasks": failed_count,
            "success_rate": f"{success_rate:.2f}%",
            "task_details": self.task_records
        }

        logger.info("=" * 60)
        logger.info("数据同步运维报告")
        logger.info(f"总任务数：{total_count} | 成功：{success_count} | 失败：{failed_count}")
        logger.info(f"成功率：{success_rate:.2f}%")
        logger.info("=" * 60)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            logger.info(f"报告已保存至：{output_file}")

        return report