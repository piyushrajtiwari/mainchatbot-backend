import html


def email_template(email: str, username: str, verification_link: str):
    """
    Email verification template - Light Theme
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ background-color: #f4f4f5; font-family: Arial, Helvetica, sans-serif; padding: 20px; margin: 0; }}
        .container {{ background: #ffffff; max-width: 520px; margin: 0 auto; padding: 36px; border-radius: 16px; border: 1px solid #e5e7eb; }}
        .logo {{ color: #7c3aed; font-size: 28px; text-align: center; font-weight: bold; margin: 0; }}
        .subtitle {{ color: #6b7280; font-size: 14px; text-align: center; margin: 8px 0 24px; }}
        .heading {{ color: #111827; font-size: 22px; margin: 0 0 12px; }}
        .text {{ color: #4b5563; font-size: 15px; line-height: 24px; margin: 0 0 16px; }}
        .box {{ background: #f9fafb; padding: 20px; border-radius: 12px; margin: 24px 0; border: 1px solid #e5e7eb; }}
        .label {{ color: #6b7280; font-size: 11px; font-weight: bold; letter-spacing: 1px; margin: 0; }}
        .value {{ color: #111827; font-size: 15px; margin: 4px 0 16px; }}
        .btn {{ background: #7c3aed; color: #ffffff !important; padding: 14px 24px; border-radius: 10px; display: block; text-align: center; text-decoration: none; font-weight: bold; font-size: 15px; margin-top: 24px; }}
        .link-text {{ color: #7c3aed; font-size: 12px; text-align: center; margin-top: 12px; word-break: break-all; }}
        .footer {{ color: #9ca3af; font-size: 12px; text-align: center; margin-top: 28px; line-height: 18px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <p class="logo">MainChatBot</p>
        <p class="subtitle">Verify Your Email</p>

        <h2 class="heading">Hi {html.escape(username,quote=True)}, Verify Your Email 👋</h2>
        <p class="text">
          Thanks for signing up. Please click the button below to verify your email address and activate your account.
        </p>

        <div class="box">
          <p class="label">USERNAME</p>
          <p class="value">{html.escape(username,quote=True)}</p>
          <p class="label">EMAIL ADDRESS</p>
          <p class="value">{html.escape(email,quote=True)}</p>
        </div>

        <a class="btn" href="{html.escape(verification_link,quote=True)}">Verify Email →</a>
        <p class="link-text">Or copy this link:<br>{html.escape(verification_link,quote=True)}</p>

        <p class="footer">
          If you did not sign up, please ignore this email.<br>
          This link will expire in 15 minutes.<br>
          © 2026 MainChatBot. All rights reserved.
        </p>
      </div>
    </body>
    </html>
    """


def password_reset_template(email: str, username: str, reset_link: str) -> str:
    """Password reset email in the same style as the verification email."""
    safe_name = html.escape(username, quote=True)
    safe_email = html.escape(email, quote=True)
    safe_link = html.escape(reset_link, quote=True)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ background-color: #f4f4f5; font-family: Arial, Helvetica, sans-serif; padding: 20px; margin: 0; }}
        .container {{ background: #ffffff; max-width: 520px; margin: 0 auto; padding: 36px; border-radius: 16px; border: 1px solid #e5e7eb; }}
        .logo {{ color: #7c3aed; font-size: 28px; text-align: center; font-weight: bold; margin: 0; }}
        .subtitle {{ color: #6b7280; font-size: 14px; text-align: center; margin: 8px 0 24px; }}
        .heading {{ color: #111827; font-size: 22px; margin: 0 0 12px; }}
        .text {{ color: #4b5563; font-size: 15px; line-height: 24px; margin: 0 0 16px; }}
        .btn {{ background: #7c3aed; color: #ffffff !important; padding: 14px 24px; border-radius: 10px; display: block; text-align: center; text-decoration: none; font-weight: bold; font-size: 15px; margin-top: 24px; }}
        .link-text {{ color: #7c3aed; font-size: 12px; text-align: center; margin-top: 12px; word-break: break-all; }}
        .footer {{ color: #9ca3af; font-size: 12px; text-align: center; margin-top: 28px; line-height: 18px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <p class="logo">MainChatBot</p>
        <p class="subtitle">Reset Your Password</p>
        <h2 class="heading">Hi {safe_name},</h2>
        <p class="text">We received a request to reset the password for {safe_email}. Click below to choose a new password.</p>
        <a class="btn" href="{safe_link}">Reset Password →</a>
        <p class="link-text">Or copy this link:<br>{safe_link}</p>
        <p class="footer">If you did not request this, you can ignore this email.<br>This link expires in 15 minutes.</p>
      </div>
    </body>
    </html>
    """
