import pika
import asyncio
import os
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from models import AudioFile
from transcription import load_audio, transcribe_audio_file
from utils import check_file_exists
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RabbitMQ connection settings
RABBITMQ_HOST = "rabbitmq"
RABBITMQ_PORT = "5672"
RABBITMQ_USERNAME = "user"
RABBITMQ_PASSWORD = "pass"
QUEUE_NAME = "audio_queue"


def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=RABBITMQ_HOST, port=int(RABBITMQ_PORT), credentials=credentials
        )
    )
    return connection


async def consume_messages():
    # Get RabbitMQ connection and create a channel
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    def callback(ch, method, properties, body):
        print(f"Received message: {body.decode()}")
        logger.info(f"Received message: {body.decode()}")
        # Process message here

    # Start consuming messages asynchronously using an executor
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback, auto_ack=True)

    print("Started consuming messages from RabbitMQ")
    # Run consuming in a background thread to prevent blocking
    await asyncio.get_event_loop().run_in_executor(None, channel.start_consuming)

    # Cleanup: Close the connection after consuming is done
    connection.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup: Start the RabbitMQ consumer in a background task when the app starts
    consumer_task = asyncio.create_task(consume_messages())
    yield
    # Cleanup: Stop the consumer task when the app shuts down
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)


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
        # You can send this message to a queue if needed
        return {"transcription": transcript}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
