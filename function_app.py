import datetime
import os
import pyodbc
import random
import logging
import requests  # Importing requests to make HTTP requests
import azure.functions as func

# Create a Function App instance to register functions
app = func.FunctionApp()

# Timer Trigger Function: log_generator
# This function runs every 10 seconds to generate log entries and add them to the SQL database
@app.function_name(name="log_generator")
@app.timer_trigger(schedule="*/10 * * * * *", arg_name="mytimer", run_on_startup=False, use_monitor=False)
def log_generator(mytimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.datetime.utcnow().replace(
        tzinfo=datetime.timezone.utc).isoformat()

    if mytimer.past_due:
        logging.info('The timer is past due!')

    # Fetch the SQL connection string from environment variables
    conn_str = os.getenv("SQL_CONNECTION_STRING")

    try:
        # Establish connection to the SQL database
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Generate a random log level and message
        log_levels = ["INFO", "WARNING", "ERROR", "CRITICAL"]
        log_level = random.choice(log_levels)
        message = f"{log_level} log generated at {datetime.datetime.now()}."

        # Insert the generated log into the Logs table
        cursor.execute("INSERT INTO Logs (LogLevel, Message) VALUES (?, ?)", log_level, message)
        conn.commit()
        logging.info(f"Log entry added: {message}")

        # If the log level is ERROR or CRITICAL, trigger the alert function
        if log_level in ["ERROR", "CRITICAL"]:
            try:
                # Send an HTTP GET request to trigger the alert function
                response = requests.get('https://my-monitoring-app.azurewebsites.net/api/alert')  # Replace with Azure Function endpoint if deployed
                logging.info(f"Alert triggered: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to trigger alert: {e}")

    except pyodbc.Error as e:
        logging.error(f"Database connection error: {e}")

    finally:
        # Ensure the database connection is closed properly
        if 'conn' in locals():
            conn.close()

    logging.info('Python timer trigger function ran at %s', utc_timestamp)


# HTTP Trigger Function: trigger_alert
# This function responds to HTTP requests and retrieves the latest ERROR or CRITICAL log from the database
@app.function_name(name="trigger_alert")
@app.route(route="alert", auth_level=func.AuthLevel.ANONYMOUS)
def trigger_alert(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('HTTP trigger function processed a request.')

    # Fetch the SQL connection string from environment variables
    conn_str = os.getenv("SQL_CONNECTION_STRING")

    try:
        # Connect to the database
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Query the latest ERROR or CRITICAL log entry
        cursor.execute("""
            SELECT TOP 1 LogLevel, Message, Timestamp 
            FROM Logs 
            WHERE LogLevel IN ('ERROR', 'CRITICAL') 
            ORDER BY Timestamp DESC
        """)
        row = cursor.fetchone()

        if row:
            # Prepare a response with the latest critical/error log
            response_message = f"[{row.Timestamp}] {row.LogLevel}: {row.Message}"
            logging.info(f"Returning latest critical/error log: {response_message}")
            return func.HttpResponse(response_message, status_code=200)
        else:
            return func.HttpResponse("No critical or error logs found.", status_code=200)

    except pyodbc.Error as e:
        logging.error(f"Database connection error: {e}")
        return func.HttpResponse(f"Database connection error: {e}", status_code=500)

    finally:
        # Ensure the database connection is closed properly
        if 'conn' in locals():
            conn.close()
