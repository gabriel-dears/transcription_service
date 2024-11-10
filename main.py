import pika
import asyncio
from fastapi import FastAPI, HTTPException
from models import AudioFile
from transcription import load_audio, transcribe_audio_file
from utils import check_file_exists

app = FastAPI()

# RabbitMQ connection settings
RABBITMQ_HOST = "rabbitmq"
RABBITMQ_PORT = 5672
RABBITMQ_USERNAME = "user"
RABBITMQ_PASSWORD = "pass"
QUEUE_NAME = "audio_queu"

def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=credentials)
    )
    return connection

def send_message_to_queue(message: str):
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=message,
        properties=pika.BasicProperties(delivery_mode=2)  # make message persistent
    )
    connection.close()

@app.get("/")
async def root():
    return {"message": "Google Speech-to-Text Service is running"}

@app.post("/transcribe")
async def transcribe_audio(audio_file: AudioFile):
    try:
        check_file_exists(audio_file.audio_path)
        audio = load_audio(audio_file.audio_path)
        transcript = transcribe_audio_file(audio)
        message = f"Transcription completed for {audio_file.audio_path}. Transcript: {transcript}"
        send_message_to_queue(message)
        return {"transcription": transcript}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

# Background task to consume messages
async def consume_messages():
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    def callback(ch, method, properties, body):
        print(f"Received message: {body.decode()}")
        # Process message here

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback, auto_ack=True)
    print("Started consuming messages from RabbitMQ")
    channel.start_consuming()

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.create_task(consume_messages())
