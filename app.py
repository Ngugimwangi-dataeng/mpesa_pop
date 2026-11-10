import os
import base64
from datetime import datetime
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

def env_value(name, default=""):
    value = os.getenv(name, default)
    if value is None:
        return default
    return value.strip()


app = Flask(__name__)
app.config["SECRET_KEY"] = env_value("SECRET_KEY", "default_secret")
app.secret_key = app.config["SECRET_KEY"]

# Database Connection Helper
def get_db_connection():
    return psycopg2.connect(
        host=env_value("DB_HOST"),
        port=env_value("DB_PORT"),
        database=env_value("DB_NAME"),
        user=env_value("DB_USER"),
        password=env_value("DB_PASSWORD")
    )


BUSINESS_NAME = "Mwananchi Marketing Agency"


def is_demo_mode():
    return (
        env_value("APP_MODE", "live").lower() == "demo"
        or not env_value("MPESA_CONSUMER_KEY")
        or not env_value("MPESA_CONSUMER_SECRET")
        or not env_value("MPESA_SHORTCODE")
    )


# Get Daraja Access Token
def get_mpesa_access_token():
    env = env_value("MPESA_ENVIRONMENT") or env_value("MPESA_ENV") or "sandbox"
    consumer_key = env_value("MPESA_CONSUMER_KEY")
    consumer_secret = env_value("MPESA_CONSUMER_SECRET")

    api_url = (
        "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
        if env == "sandbox"
        else "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    )

    try:
        auth_pair = (consumer_key, consumer_secret)
        print(f"Daraja auth URL: {api_url}")
        print(f"Daraja auth pair length: {len(auth_pair)}")
        print(f"Daraja key present: {bool(consumer_key)}")
        print(f"Daraja secret present: {bool(consumer_secret)}")
        response = requests.get(api_url, auth=auth_pair, timeout=10)
        print(f"Daraja token response status: {response.status_code}")
        print(f"Daraja token response body: {response.text}")
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(f"Error getting access token: {e}")
        try:
            print(f"Daraja error body: {response.text}")
        except Exception:
            pass
        return None

# Generate Password and Timestamp
def generate_mpesa_password():
    shortcode = env_value("MPESA_SHORTCODE")
    passkey = env_value("MPESA_PASSKEY")
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    data_to_encode = f"{shortcode}{passkey}{timestamp}"
    encoded_string = base64.b64encode(data_to_encode.encode()).decode("utf-8")
    return encoded_string, timestamp

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/v1/mpesa/stkpush", methods=["POST"])
def initiate_stk_push():
    data = request.get_json()
    phone = data.get("phone")
    amount = data.get("amount")

    if not phone or not amount:
        return jsonify({"status": "error", "message": "Phone number and amount are required"}), 400

    # Format phone number to 2547XXXXXXXX
    phone = phone.strip().replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7") or phone.startswith("1"):
        phone = "254" + phone

    if is_demo_mode():
        checkout_id = f"DEMO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO mpesa_transactions
                (merchant_request_id, checkout_request_id, phone_number, amount, account_reference, transaction_status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (None, checkout_id, phone, amount, BUSINESS_NAME, "PENDING")
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as exc:
            print(f"Demo DB save skipped: {exc}")
        return jsonify({
            "status": "success",
            "message": f"Demo mode active: STK push simulated successfully for {BUSINESS_NAME}. Add real M-Pesa credentials to connect to Safaricom.",
            "checkout_id": checkout_id
        })

    access_token = get_mpesa_access_token()
    if not access_token:
        error_details = f"Failed to authenticate with M-Pesa for {BUSINESS_NAME}"
        try:
            response = requests.get(
                (
                    "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
                    if (os.getenv("MPESA_ENVIRONMENT") or os.getenv("MPESA_ENV") or "sandbox") == "sandbox"
                    else "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
                ),
                auth=(os.getenv("MPESA_CONSUMER_KEY"), os.getenv("MPESA_CONSUMER_SECRET")),
                timeout=10,
            )
            if response.text:
                error_details = f"{response.text} for {BUSINESS_NAME}"
        except Exception:
            pass
        return jsonify({"status": "error", "message": error_details}), 500

    password, timestamp = generate_mpesa_password()
    env = env_value("MPESA_ENVIRONMENT") or env_value("MPESA_ENV") or "sandbox"
    shortcode = env_value("MPESA_SHORTCODE")

    stk_url = (
        "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        if env == "sandbox"
        else "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(float(amount)),
        "PartyA": phone,
        "PartyB": shortcode,
        "PhoneNumber": phone,
        "CallBackURL": env_value("MPESA_CALLBACK_URL"),
        "AccountReference": BUSINESS_NAME,
        "TransactionDesc": f"Payment to {BUSINESS_NAME}"
    }

    try:
        res = requests.post(stk_url, json=payload, headers=headers, timeout=15)
        res_data = res.json()

        if res_data.get("ResponseCode") == "0":
            checkout_id = res_data.get("CheckoutRequestID")
            merchant_id = res_data.get("MerchantRequestID")

            # Save initial pending record in database
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO mpesa_transactions
                (merchant_request_id, checkout_request_id, phone_number, amount, account_reference, transaction_status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (merchant_id, checkout_id, phone, amount, BUSINESS_NAME, "PENDING")
            )
            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                "status": "success",
                "message": "STK Push sent successfully. Enter PIN on your phone.",
                "checkout_id": checkout_id
            })
        else:
            return jsonify({
                "status": "error",
                "message": res_data.get("ResponseDescription", f"Failed to send STK Push for {BUSINESS_NAME}")
            }), 400

    except Exception as e:
        print(f"STK Push Error: {e}")
        return jsonify({"status": "error", "message": "Server processing error"}), 500

@app.route("/api/v1/mpesa/callback", methods=["POST"])
def mpesa_callback():
    data = request.get_json()
    print("M-Pesa Callback Data Received:", data)

    try:
        stk_callback = data.get("Body", {}).get("stkCallback", {})
        result_code = stk_callback.get("ResultCode")
        result_desc = stk_callback.get("ResultDesc")
        checkout_id = stk_callback.get("CheckoutRequestID")

        mpesa_receipt = None

        if result_code == 0:
            status = "SUCCESS"
            items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
            for item in items:
                if item.get("Name") == "MpesaReceiptNumber":
                    mpesa_receipt = item.get("Value")
        else:
            status = "CANCELLED" if result_code == 1032 else "FAILED"

        # Update database entry
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE mpesa_transactions
            SET transaction_status = %s, result_code = %s, result_desc = %s,
                mpesa_receipt_number = %s, updated_at = CURRENT_TIMESTAMP
            WHERE checkout_request_id = %s
            """,
            (status, result_code, result_desc, mpesa_receipt, checkout_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

    except Exception as e:
        print(f"Callback Error: {e}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Failed"}), 500

@app.route("/api/v1/mpesa/check-status/<checkout_id>", methods=["GET"])
def check_status(checkout_id):
    if checkout_id.startswith("DEMO-"):
        return jsonify({
            "status": "success",
            "data": {
                "transaction_status": "SUCCESS",
                "mpesa_receipt_number": "DEMO-RECEIPT",
                "result_desc": "Demo mode payment simulation succeeded."
            }
        })

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT transaction_status, mpesa_receipt_number, result_desc FROM mpesa_transactions WHERE checkout_request_id = %s", (checkout_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            return jsonify({"status": "success", "data": row})
        return jsonify({"status": "error", "message": "Transaction not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(env_value("PORT", "5000")), debug=True)
