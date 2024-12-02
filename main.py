import asyncio
import base64
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

import pika
import psycopg2
from fastapi import FastAPI, HTTPException

from models import AudioFile, AudioChunkMessage
from transcription import load_audio, transcribe_audio_file
from utils import check_file_exists

# Database connection parameters
DB_HOST = "transcription_service_db_postgres"
DB_NAME = "transcription_service_db"
DB_USER = "postgres"
DB_PASSWORD = "postgres"


# Establish a connection to the database
def get_db_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST
    )
    return conn


# Function to insert transcription into the database
def insert_transcription(channel_id, video_id, part, transcription, tags, category):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # SQL query to insert the transcription record
        insert_query = """
        INSERT INTO transcriptions (channel_id, video_id, part, transcription, tags, category, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        # Prepare the data for insertion
        current_time = datetime.now()
        tags_array = tags  # Assuming 'tags' is a list or array
        data = (channel_id, video_id, part, transcription, tags_array, category, current_time, current_time)

        # Execute the query
        cursor.execute(insert_query, data)

        # Commit the transaction
        conn.commit()

        # Close the cursor and connection
        cursor.close()
        conn.close()

        print(f"Transcription for video {video_id} part {part} inserted successfully.")

    except Exception as e:
        print(f"Error inserting transcription: {e}")
        if conn:
            conn.rollback()


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

        processed_message = {
            "channelId": audio_chunk_message.channelId,
            "videoId": audio_chunk_message.videoId,
            "transcription": transcript,
            "tags": audio_chunk_message.tags,
            "category": audio_chunk_message.category,
        }

        # Store transcribed content
        # TODO: get "part" from audio_generator_service
        insert_transcription(audio_chunk_message.channelId, audio_chunk_message.videoId, 1, processed_message,
                             audio_chunk_message.tags, audio_chunk_message.category)

        # Send the message to the next queue
        send_to_queue("transcription_queue", processed_message)

        # Log the transcript
        # logger.info(f"Transcription completed for {audio_chunk_message.channelId}_{audio_chunk_message.videoId}.")
        # logger.info(f"Transcript: {transcript}")

        # You can return or send the transcript to another queue if needed
        return transcript
    except Exception as e:
        logger.error(
            f"Failed to transcribe audio chunk for {audio_chunk_message.channelId}_{audio_chunk_message.videoId}: {e}")


def send_to_queue(queue_name: str, message: dict):
    try:
        # Establish RabbitMQ connection
        connection = get_rabbitmq_connection()
        channel = connection.channel()

        # Declare the exchange
        exchange_name = "transcription_exchange"
        channel.exchange_declare(
            exchange=exchange_name,
            exchange_type="direct",  # Use the appropriate type (e.g., direct, fanout, topic)
            durable=True  # Make it persistent
        )

        # Declare the queue
        channel.queue_declare(queue=queue_name, durable=True)

        # Bind the queue to the exchange
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        # Publish the message to the exchange
        channel.basic_publish(
            exchange=exchange_name,
            routing_key=queue_name,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            ),
        )

        logger.info(f"Message sent to queue '{queue_name}': {message}")

        # Close the connection
        connection.close()
    except Exception as e:
        logger.error(f"Failed to send message to queue '{queue_name}': {e}")
        raise e


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
