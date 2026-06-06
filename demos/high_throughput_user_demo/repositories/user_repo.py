from sqlalchemy.orm import Session
from models.user_model import UserModel

class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def fast_bulk_insert(self, data_list: list[dict]) -> int:
        """
        王者级！使用 bulk_insert_mappings 极致批量落库。
        直接操作 mapping，不触发对象的各种事件和状态跟踪，极大节约内存。
        """
        if not data_list:
            return 0
            
        try:
            # bulk_insert_mappings is extremely fast for bulk pure inserts
            self.session.bulk_insert_mappings(UserModel, data_list)
            self.session.commit()
            return len(data_list)
        except Exception as e:
            self.session.rollback()
            # 在实际业务中，可以记录到日志，或将失败的批次放入死信队列 (Dead Letter Queue)
            print(f"[Repo Error] Bulk insert failed: {e}")
            raise e
