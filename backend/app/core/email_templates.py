"""Simple, on-brand HTML email templates."""


def _wrap(heading: str, message: str, button_text: str, button_url: str) -> str:
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;background:#000;color:#fff;font-family:Inter,Arial,sans-serif;">
    <div style="max-width:520px;margin:0 auto;padding:40px 24px;">
      <div style="font-size:22px;font-weight:800;letter-spacing:-0.5px;margin-bottom:28px;">
        NEXUS<span style="color:#555;font-weight:300;">PRO</span>
      </div>
      <div style="background:#0a0a0a;border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:32px;">
        <h1 style="font-size:20px;margin:0 0 12px;">{heading}</h1>
        <p style="color:#aaa;font-size:14px;line-height:1.6;margin:0 0 24px;">{message}</p>
        <a href="{button_url}"
           style="display:inline-block;background:#fff;color:#000;text-decoration:none;
                  font-weight:700;font-size:14px;padding:12px 24px;border-radius:999px;">
          {button_text}
        </a>
        <p style="color:#555;font-size:12px;line-height:1.6;margin:24px 0 0;">
          If the button doesn't work, paste this link into your browser:<br>
          <span style="color:#06b6d4;word-break:break-all;">{button_url}</span>
        </p>
      </div>
      <p style="color:#444;font-size:11px;text-align:center;margin-top:24px;">
        If you didn't request this, you can safely ignore this email.
      </p>
    </div>
  </body>
</html>"""


def verification_email(link: str) -> tuple[str, str, str]:
    subject = "Verify your email — NEXUS"
    html = _wrap(
        "Verify your email",
        "Confirm your email address to unlock uploads, gems, and VIP features.",
        "Verify email",
        link,
    )
    text = f"Verify your email: {link}"
    return subject, html, text


def password_reset_email(link: str) -> tuple[str, str, str]:
    subject = "Reset your password — NEXUS"
    html = _wrap(
        "Reset your password",
        "We received a request to reset your password. This link expires in 1 hour.",
        "Reset password",
        link,
    )
    text = f"Reset your password: {link}"
    return subject, html, text
