import pika
import asyncio
import os
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from models import AudioFile, AudioChunkMessage
from transcription import load_audio, transcribe_audio_file
from utils import check_file_exists
import logging
import json
import base64
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RabbitMQ connection settings
RABBITMQ_HOST = os.getenv('SPRING_RABBITMQ_HOST')
RABBITMQ_PORT = os.getenv('SPRING_RABBITMQ_PORT')
RABBITMQ_USERNAME = os.getenv('SPRING_RABBITMQ_USERNAME')
RABBITMQ_PASSWORD = os.getenv('SPRING_RABBITMQ_PASSWORD')
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
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    def callback(ch, method, properties, body):
        try:
            message_data = json.loads(body.decode("utf-8"))
            audio_chunk_message = AudioChunkMessage(**message_data)

            # Process the audio chunk and transcribe
            process_and_transcribe_audio(audio_chunk_message)

            # Acknowledge the message
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except json.JSONDecodeError as json_error:
            logger.error(f"Failed to decode JSON: {json_error}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Failed to process message: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback, auto_ack=False)

    logger.info("Started consuming messages from RabbitMQ")
    await asyncio.get_event_loop().run_in_executor(None, channel.start_consuming)
    connection.close()


def process_and_transcribe_audio(audio_chunk_message: AudioChunkMessage):
    try:
        # Decode the base64 audio chunk into a byte array
        audio_data = base64.b64decode(audio_chunk_message.audioChunk)

        # Create an in-memory file-like object from the byte array
        audio_file_obj = io.BytesIO(audio_data)

        # Load and transcribe the audio directly from the in-memory object
        audio = load_audio(audio_file_obj)
        transcript = transcribe_audio_file(audio)

        # Log the transcript
        logger.info(f"Transcription completed for {audio_chunk_message.channelId}_{audio_chunk_message.videoId}.")
        logger.info(f"Transcript: {transcript}")

        # You can return or send the transcript to another queue if needed
        return transcript
    except Exception as e:
        logger.error(f"Failed to transcribe audio chunk for {audio_chunk_message.channelId}_{audio_chunk_message.videoId}: {e}")

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
