# 🔐 Social Media Credentials Setup Guide

> This document covers how to obtain API credentials for each supported integration: Telegram, WhatsApp (Meta Cloud API), LinkedIn (OAuth — handled by backend), and Slack.

---

## 📬 1. Telegram — Bot Token & Chat ID

### What You Need
| Field | Description |
|---|---|
| `bot_token` | Unique token for your bot |
| `chat_id` | ID of the chat where messages will be sent |

---

### Step 1: Create a Bot via BotFather

1. Open **Telegram** on any device.
2. In the search bar, search for **`@BotFather`** and open that chat.
3. Send the command:
   ```
   /newbot
   ```
4. BotFather will ask for a **bot name** (e.g., `My Notifier Bot`) — enter it.
5. Next, it will ask for a **username** — this must:
   - Be unique
   - End with `bot` (e.g., `mynotifier_bot`)
6. After successful creation, BotFather replies with a message containing your **Bot Token** in this format:
   ```
   123456789:ABCDefgh-IJKLMNO_pqrstuvwxyz123456
   ```
7. **Copy and save this token.**

---

### Step 2: Get Your Chat ID

1. Open your newly created bot in Telegram.
2. Send any message (e.g., `/start` or `hello`).
3. Open the following URL in your browser (replace `<YOUR_TOKEN>` with your actual token):
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
4. You will see a JSON response. Look for the `"chat"` object inside `"message"`:
   ```json
   {
     "message": {
       "chat": {
         "id": 987654321,
         ...
       }
     }
   }
   ```
5. **Copy the value of `"id"` — that is your Chat ID.**

> ⚠️ If the response is empty (`{"ok":true,"result":[]}`), go back to Telegram, send another message to your bot, then refresh the URL.

---

### Credentials to Store

```json
{
  "bot_token": "123456789:ABCDefgh-IJKLMNO_pqrstuvwxyz123456",
  "chat_id": "987654321"
}
```

---

## 💬 2. WhatsApp — Meta Cloud API

### What You Need
| Field | Description |
|---|---|
| `access_token` | System user token (permanent) or temporary token (dev only) |
| `phone_number_id` | ID of the WhatsApp phone number in your Meta app |
| `waba_id` | WhatsApp Business Account ID |

---

### Step 1: Create a Meta Developer Account

1. Go to [https://developers.facebook.com](https://developers.facebook.com).
2. Click **Get Started** (top right).
3. Log in with your **Facebook account**.
4. Complete email verification if prompted.
5. You are now on the **Meta Developer dashboard**.

---

### Step 2: Create a New App

1. On the dashboard, click **My Apps** → **Create App**.
2. Under **Use case**, select:
   > **"Other"** → then on the next screen select **"Business"**
3. Fill in the app details:
   - **App Name**: anything descriptive (e.g., `MyProject WA`)
   - **Contact email**: your email
4. Click **Create App**.

---

### Step 3: Add WhatsApp to Your App

1. Inside your newly created app's dashboard, scroll down to find **"Add Products to Your App"**.
2. Find **WhatsApp** and click **Set Up**.
3. You will be redirected to the **WhatsApp Getting Started** page inside your app.

---

### Step 4: Link a WhatsApp Business Account (WABA)

1. On the WhatsApp Getting Started page, you'll be prompted to select or create a **WhatsApp Business Account**.
2. If you don't have one, click **Create new** and enter a **Business Portfolio Name**.
3. Click **Continue** / **Next** until setup is complete.
4. You will now see your:
   - **Temporary Access Token** (valid for ~24 hours)
   - **Phone Number ID** (for the test number provided by Meta)
   - **WhatsApp Business Account ID (WABA ID)**

> 📌 Copy all three values. They are visible on the **API Setup** page within WhatsApp > Getting Started.

---

### Step 5: Add a Recipient for Testing

1. Still on the Getting Started page, find the **"To"** section.
2. Click **"Add phone number"** and enter your personal WhatsApp number (with country code, e.g., `+919876543210`).
3. You'll receive a verification code on WhatsApp — enter it to verify.

---

### Step 6: Send a Test Message

Use the following `curl` command to verify your setup (replace the placeholders):

```bash
curl -X POST https://graph.facebook.com/v18.0/<PHONE_NUMBER_ID>/messages \
  -H "Authorization: Bearer <TEMPORARY_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "<YOUR_WHATSAPP_NUMBER_WITH_COUNTRY_CODE>",
    "type": "template",
    "template": {
      "name": "hello_world",
      "language": { "code": "en_US" }
    }
  }'
```

✅ If you receive the message on WhatsApp — your credentials are working.

> ⚠️ `hello_world` is a pre-approved template provided by Meta. You don't need to create it.

---

### Step 7: Generate a Permanent Access Token (For Production)

Temporary tokens expire in ~24 hours. For production use, generate a **System User Token**:

1. Go to [https://business.facebook.com](https://business.facebook.com) → **Business Settings**.
2. In the left sidebar, go to **Users** → **System Users**.
3. Click **Add** → enter a name → set role to **Admin** → click **Create System User**.
4. Click on the system user you just created → click **Generate New Token**.
5. Select your **App** from the dropdown.
6. Enable these permissions:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
7. Click **Generate Token** and **copy the token immediately** (it won't be shown again).

---

### Step 8: Create and Get a Message Template Approved

> ⚠️ WhatsApp only allows pre-approved templates for outbound messages to users who haven't messaged you first.

1. Go to [https://business.facebook.com/wa/manage/message-templates](https://business.facebook.com/wa/manage/message-templates).
2. Select your **WhatsApp Business Account**.
3. Click **Create Template**.
4. Fill in:
   - **Category**: e.g., `Marketing`, `Utility`, or `Authentication`
   - **Name**: lowercase, underscores only (e.g., `order_confirmation`)
   - **Language**: select your language
   - **Content**: write the template body (use `{{1}}`, `{{2}}` for variables)
5. Click **Submit**.
6. Approval usually takes a few minutes to a few hours.

---

### Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| `Invalid OAuth access token` | Token expired | Regenerate a permanent system user token |
| `Template not found` or `template_not_approved` | Template pending or rejected | Check template status in WhatsApp Manager |
| `Invalid phone number` | Missing country code | Use format `+919876543210` |
| `Unsupported request` | Using personal WhatsApp number as sender | Only registered WhatsApp Business numbers work |

---

### Credentials to Store

```json
{
  "access_token": "EAAxxxxxxxxxxxxxxx",
  "phone_number_id": "1234567890123456",
  "waba_id": "9876543210987654"
}
```

---

## 💼 3. LinkedIn — OAuth 2.0 (Backend-Handled)

> ✅ **No manual credential collection is needed from the user.**
>
> LinkedIn uses **OAuth 2.0**, which means the authentication flow is handled entirely by the backend. The user simply clicks "Connect LinkedIn" in the UI, gets redirected to LinkedIn to approve access, and the backend receives and stores the access token automatically.

---

### How It Works (For Developer Reference)

1. The backend redirects the user to LinkedIn's OAuth authorization URL:
   ```
   https://www.linkedin.com/oauth/v2/authorization
     ?response_type=code
     &client_id=<YOUR_CLIENT_ID>
     &redirect_uri=<YOUR_REDIRECT_URI>
     &scope=openid%20profile%20email%20w_member_social
   ```
2. The user logs in to LinkedIn and approves the requested permissions.
3. LinkedIn redirects back to your `redirect_uri` with an `authorization_code`.
4. The backend exchanges this code for an `access_token` via:
   ```
   POST https://www.linkedin.com/oauth/v2/accessToken
   ```
5. The backend stores the `access_token` in the `app_credentials` table linked to the user's account.

---

### Backend Setup (One-Time, Done by Developer)

1. Go to [https://www.linkedin.com/developers](https://www.linkedin.com/developers).
2. Click **Create App**.
3. Fill in:
   - **App Name**
   - **LinkedIn Page** (requires a LinkedIn Company Page)
   - **App Logo**
4. After creation, go to the **Auth** tab:
   - Copy the **Client ID** and **Client Secret** (stored in backend `.env` only)
   - Add your **Redirect URL** (e.g., `https://yourapp.com/auth/linkedin/callback`)
5. Under the **Products** tab, request access to:
   - **Sign In with LinkedIn using OpenID Connect**
   - **Share on LinkedIn**
   *(These may require a short review period)*

---

### Credentials Stored (Backend Only — Not User-Facing)

```env
LINKEDIN_CLIENT_ID=your_client_id
LINKEDIN_CLIENT_SECRET=your_client_secret
LINKEDIN_REDIRECT_URI=https://yourapp.com/auth/linkedin/callback
```

> The user's `access_token` is stored in `app_credentials` after OAuth flow completes — the user never needs to paste it manually.

---

## 💬 4. Slack — Bot Token

### What You Need
| Field | Description |
|---|---|
| `bot_token` | OAuth token for your Slack bot (starts with `xoxb-`) |

---

### Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps).
2. Click **Create New App**.
3. Choose **From scratch**.
4. Enter:
   - **App Name**: e.g., `MyNotifier`
   - **Workspace**: select the Slack workspace you want to install it in
5. Click **Create App**.

---

### Step 2: Set Bot Permissions (OAuth Scopes)

1. In the left sidebar, click **OAuth & Permissions**.
2. Scroll down to **Bot Token Scopes**.
3. Click **Add an OAuth Scope** and add the following:

| Scope | Purpose |
|---|---|
| `chat:write` | Send messages to channels |
| `channels:read` | List public channels |
| `channels:join` | Join public channels (optional) |

---

### Step 3: Install App to Workspace

1. Scroll back up on the **OAuth & Permissions** page.
2. Click **Install to Workspace**.
3. Review the permissions and click **Allow**.
4. After installation, you'll see the **Bot User OAuth Token** on the same page:
   ```
    YOUR_SLACK_BOT_TOKEN
   ```
5. **Copy this token.**

---

### Step 4: Get the Channel ID (if needed)

1. Open Slack in the browser.
2. Navigate to the channel you want to post to.
3. The URL will look like:
   ```
   https://app.slack.com/client/TXXXXXXXX/CXXXXXXXXX
   ```
4. The part starting with `C` is the **Channel ID**.

> Alternatively: Right-click the channel name → **View channel details** → scroll to the bottom to find the Channel ID.

---

### Common Errors & Fixes

| Error | Cause | Fix |
|---|---|---|
| `not_in_channel` | Bot hasn't joined the channel | Invite the bot: `/invite @YourBotName` |
| `channel_not_found` | Wrong channel ID or bot lacks access | Double-check channel ID and scopes |
| `invalid_auth` | Token is wrong or revoked | Reinstall the app and copy the new token |

---

### Credentials to Store

```json
{
  "bot_token": "YOUR_SLACK_BOT_TOKEN"
}
```

---

## 🗄️ How Credentials Fit in the System

| Platform | Stored Fields | Notes |
|---|---|---|
| Telegram | `bot_token`, `chat_id` | User provides both |
| WhatsApp | `access_token`, `phone_number_id`, `waba_id` | Use system user token for production |
| LinkedIn | `access_token` (auto) | Backend stores after OAuth — user only clicks "Connect" |
| Slack | `bot_token` | User provides after installing app to workspace |

All credentials are stored in the `app_credentials` table as **JSONB**, linked via `credential_id` to the relevant node. At execution time, the backend fetches and injects them into the API call.