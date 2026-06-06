import _path  # noqa: F401

import time

from schemas.user import UserDTO
from broker.mq_client import broker_instance

def generate_and_push_data(total_records: int = 300000):
    """
    模拟一个极高吞吐量的生产者，生成 30 万条数据并丢入消息队列。
    如果是 HTTP 接口，这个过程将瞬间完成，绝大多数时间只是序列化并入队列。
    """
    print(f"[START] Producer starting: Generating {total_records} records to Redis...")
    start_time = time.time()
    
    # Using generator to avoid OOM even during generation
    def data_generator():
        for i in range(total_records):
            yield {
                "username": f"user_generated_{i}",
                "email": f"user{i}@bigtech.com",
                "age": (i % 50) + 18,
                "status": 1
            }

    success_count = 0
    # Process data pipeline
    for raw_dict in data_generator():
        try:
            # 1. Pydantic validation: Ensure the structure is pristine!
            # If a field is bad, it drops here, protecting the MQ and DB.
            validated_dto = UserDTO(**raw_dict)
            
            # 2. Push pure dict to queue
            # mode='json' ensures EmailStr and other types are converted to primitives
            broker_instance.push_message(validated_dto.model_dump(mode='json'))
            success_count += 1
            
            if success_count % 50000 == 0:
                print(f"   -> Pushed {success_count} records...")
                
        except Exception as e:
            print(f"[ERROR] Validation failed for row {raw_dict}: {e}")

    elapsed = time.time() - start_time
    print(f"[FINISHED] Producer finished! Pushed {success_count} valid records in {elapsed:.2f} seconds.")
    print(f"队列当前积压容量: {broker_instance.queue_size()}")

if __name__ == "__main__":
    generate_and_push_data(300000)
