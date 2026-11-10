document.getElementById('paymentForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    const phone = document.getElementById('phone').value;
    const amount = document.getElementById('amount').value;
    const payBtn = document.getElementById('payBtn');
    const btnText = document.getElementById('btnText');
    const alertBox = document.getElementById('alertBox');

    // Reset Alert
    alertBox.className = 'alert hidden';
    alertBox.innerText = '';

    // Disable button during process
    payBtn.disabled = true;
    btnText.innerText = 'Sending Prompt...';

    try {
        const response = await fetch('/api/v1/mpesa/stkpush', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ phone, amount })
        });

        const data = await response.json();

        if (data.status === 'success') {
            showAlert('info', 'STK push sent! Check your phone and enter your M-Pesa PIN.');
            btnText.innerText = 'Waiting for PIN...';

            // Poll for payment status
            pollPaymentStatus(data.checkout_id);
        } else {
            showAlert('error', data.message || 'Payment initiation failed.');
            payBtn.disabled = false;
            btnText.innerText = 'Pay Now';
        }
    } catch (err) {
        showAlert('error', 'Network error. Please try again.');
        payBtn.disabled = false;
        btnText.innerText = 'Pay Now';
    }
});

function pollPaymentStatus(checkoutId) {
    let attempts = 0;
    const maxAttempts = 15; // 30 seconds max polling time

    const interval = setInterval(async () => {
        attempts++;
        try {
            const res = await fetch(`/api/v1/mpesa/check-status/${checkoutId}`);
            const result = await res.json();

            if (result.status === 'success') {
                const status = result.data.transaction_status;

                if (status === 'SUCCESS') {
                    clearInterval(interval);
                    showAlert('success', `Payment received! M-Pesa Ref: ${result.data.mpesa_receipt_number}`);
                    resetButton();
                } else if (status === 'CANCELLED' || status === 'FAILED') {
                    clearInterval(interval);
                    showAlert('error', `Payment Failed: ${result.data.result_desc}`);
                    resetButton();
                }
            }
        } catch (e) {
            console.error('Polling error', e);
        }

        if (attempts >= maxAttempts) {
            clearInterval(interval);
            showAlert('info', 'Payment status pending. Check your M-Pesa SMS for confirmation.');
            resetButton();
        }
    }, 2000);
}

function showAlert(type, message) {
    const alertBox = document.getElementById('alertBox');
    alertBox.className = `alert ${type}`;
    alertBox.innerText = message;
}

function resetButton() {
    const payBtn = document.getElementById('payBtn');
    const btnText = document.getElementById('btnText');
    payBtn.disabled = false;
    btnText.innerText = 'Pay Now';
}
