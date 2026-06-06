import time
import sys
import os

# Add project root to sys.path if run directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker.mq_client import broker_instance
from repositories.user_repo import UserRepository
from db.session import SessionLocal
from config.settings import settings

class DatabaseWorker:
    def __init__(self, broker, batch_limit=None):
        self.broker = broker
        self.batch_limit = batch_limit or settings.WORKER_BATCH_SIZE

    def start_listen(self):
        print(f"[START] Worker started! Listening on Redis Queue: '{self.broker.queue_name}'...")
        print(f"[INFO] Batch strategy: bulk insert every {self.batch_limit} items.")
        
        buffer = []
        
        while True:
            try:
                # 1. Block and wait for messages (timeout 1s to prevent total deadlock)
                msg_dict = self.broker.pop_message(timeout=1)
                
                if msg_dict:
                    buffer.append(msg_dict)
                    
                # 2. Flush strategy
                # Condition A: Buffer is full
                # Condition B: Buffer has items AND we timed out getting new msgs (avoid starvation)
                buffer_is_full = len(buffer) >= self.batch_limit
                should_flush_remainder = len(buffer) > 0 and msg_dict is None
                
                if buffer_is_full or should_flush_remainder:
                    # Allocate a database session
                    db_session = SessionLocal()
                    repo = UserRepository(db_session)
                    
                    try:
                        inserted = repo.fast_bulk_insert(buffer)
                        print(f"[SUCCESS] Executed bulk insert: {inserted} records. Buffer cleared.")
                        buffer.clear()
                    finally:
                        db_session.close() # Always return the connection to the pool

                # Small sleep if completely idle to prevent CPU spin
                if msg_dict is None and len(buffer) == 0:
                    time.sleep(0.1)
                    
            except KeyboardInterrupt:
                print("Worker shutting down gracefully...")
                break
            except Exception as e:
                print(f"[ERROR] Unhandled Worker Exception: {e}")
                time.sleep(1) # Prevent tight crash loops

if __name__ == "__main__":
    worker = DatabaseWorker(broker_instance)
    worker.start_listen()
