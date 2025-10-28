# Green Smart Home API

## Overview

The Green Smart Home API is a FastAPI-based application backend compatible with Home Assistant that offers various features .It monitors appliance usage, tracks energy consumption, and enforces power thresholds to replicate real-world home automation scenarios.

The system relies on **SQLite** databases to manage consumption data, configuration, and simulation logs.
You can access the the documentations and try-out page for the API at `http://$HOST:$PORT` 



## Running the Application

To start the server, run:

```bash
python server.py
```

Make sure all dependencies are installed before running the application (see [Requirements](https://www.notion.so/299c9fbbe34f802ca944c5af8564d1cf?pvs=21)).



## Configuration

Configuration is handled through environment variables defined in a `.env` file.

A sample file, `.env.example`, is provided in the repository. You can create your own configuration by copying it:

```bash
cp .env.example .env

```

Then edit `.env` to match your environment and preferences.

### Environment Variables

| Variable | Description |
| --- | --- |
| `JWT_SECRET_KEY` | Secret key used to sign JWT authentication tokens. |
| `JWT_TOKEN_EXPIRE_MINUTES` | Token lifetime in minutes. |
| `W_TO_GCO2` | Conversion factor between watt-hours and CO₂ emissions (in grams per Wh). The default value corresponds to Italy. |
| `W_TO_GCO2_UNIT` | Unit of measurement for the CO₂ conversion rate (e.g., `kgCO2/kWh`). |
| `ENABLE_PREDICTION` | Enables TensorFlow-based prediction APIs (1 = enabled, 0 = disabled). |
| `ENABLE_DEMO` | Loads a demo smart home configuration from sample files instead of a live Home Assistant instance (1 = enabled, 0 = disabled). |
| `ENABLE_AUTHENTICATION` | Enables JWT-based authentication for all endpoints (1 = enabled, 0 = disabled). |
| `HOST` | The hostname or IP address the FastAPI server will bind to. |
| `PORT` | The port number the server will listen on. |
| `MONGOURL` | Connection string for the MongoDB instance (optional, used for extended data storage). |
| `MYSQL_HOST` | MySQL database host (used for external authentication or data integration). |
| `MYSQL_USER` | MySQL database username. |
| `MYSQL_PASSWORD` | MySQL database password. |
| `MYSQL_DATABASE` | MySQL database name. |

---

## Directory Structure

```
├── server.py                     # Main FastAPI server script
├── .env.example                  # Example environment configuration file
├── requirements.txt              # Python dependencies
├── data/                         # Databases, configuration, and simulation context
│   ├── appliances_consumption_map.json   # Maps appliance types to power usage
│   ├── devices_new_state_map.json        # Defines state transitions for smart devices
│   ├── digital_twin_configuration.db     # Stores house configuration (thresholds, energy tariffs, HA parameters)
│   ├── digital_twin_consumption.db       # Records per-device energy usage and duration
│   ├── digital_twin_entity_history.db    # Tracks state changes and entity history over time
│   ├── digital_twin_logs.db              # Contains users logs
│   ├── entities_consumption_map.json     # Maps entities to their energy consumption models
│   └── virtual_context.json              # Defines simulated environment context and entities

```



## Requirements

Before running the application, install all dependencies using:

```bash
pip install -r requirements.txt
```



## Periodic Data Collection

The script **`periodic_functions.py`** is designed to be executed periodically to update the simulation datasets.

It extracts new device histories, computes usage statistics, and logs entity activity into the corresponding SQLite databases.

### Main Features

- Retrieves device and entity history from Home Assistant via API calls
- Computes average usage durations, standby thresholds, and power levels per device
- Logs device history, entity state transitions, and appliance usage
- Writes all collected data into the respective SQLite databases within `data/`
- Generates detailed log files in `./logs/periodic_functions.log`

### Usage

Run the script manually with:

```bash
python periodic_functions.py
```

Or, for automated periodic execution (recommended), you can:

- Schedule it via **cron** or **systemd**, or
- Run it periodically inside the same **Docker container** as the main server.

### Notes

- Devices from Home Assistant **must provide a power entity** (or be attached to a power helper) for correct consumption tracking.
- Thresholds and timing constants (e.g., `STATE_CHANGE_TOLERANCE`, `ACTIVATION_TRESHOLD`) are defined at the top of the script and can be adjusted if needed.
- Logs are written both to the console and to `logs/periodic_functions.log`.



## Home Assistant Integration

To enable live integration with a Home Assistant instance, the server must be configured using the dedicated API endpoint:

```
PUT /homeassistant
```

This endpoint allows the system to connect to your Home Assistant installation and fetch entities, sensors, and real-time device data.

Once configured, the server can automatically update appliance states and consumption statistics using live inputs.

### Requirements

- The `.env` variable `ENABLE_DEMO` **must be set to `0`**.
    
    If demo mode is enabled, the `/homeassistant` integration will be ignored.
    
- The endpoint must receive a valid JSON body containing the **Home Assistant base URL** and an **access token**.

### Example Request

**Request Body:**

```json
{
  "token": "string",
  "server_url": "string"
}

```

**Example `curl` command:**

```bash
curl -X 'PUT' \
  'http://$HOST:$PORT/homeassistant' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "token": "your_long_lived_access_token_here",
    "server_url": "http://homeassistant.local:8123/api"
  }'
```

After a successful call, the connection details are stored in the configuration database and used for all subsequent data synchronization and history updates (e.g., when running periodic background functions).

### Notes

- Make sure the Home Assistant URL includes the `/api` suffix.
- The `token` must be a valid **Long-Lived Access Token** generated from your Home Assistant user profile.
- Re-sending the same request will update the stored configuration.
- If the connection fails, verify that the Home Assistant instance is reachable from the server and that the token has appropriate permissions.



## Authentication System

The application includes a built-in authentication module that can act as a **simple JWT-based identity provider**.

Authentication can be enabled or disabled globally through the `.env` configuration.

### Enabling Authentication

Set the following in your `.env` file:

```python
ENABLE_AUTHENTICATION=1
```

When enabled, all protected endpoints require a valid JWT token in the `Authorization` header (using the `Bearer` scheme).

Tokens are signed with the secret key defined in:

- `JWT_SECRET_KEY`
- `JWT_TOKEN_EXPIRE_MINUTES` (token lifetime, in minutes)
- `JWT_ALGORITHM` (default: `HS256`, set internally)



### Endpoints

### **POST /auth/login**

Authenticates a user and returns a JWT token.

**Request body:**

```json
{
  "email": "user@example.com",
  "password": "your_password"
}

```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

The token must be included in subsequent requests:

```
Authorization: Bearer <access_token>
```



### **PUT /auth/register**

Registers a new user either in **SQLite** or **MySQL**, depending on the `use_sqlite` flag in the request body.

Passwords are automatically hashed in **Laravel-compatible format** (`$2y$`).

**Example request:**

```json
{
  "username": "JohnDoe",
  "email": "john@example.com",
  "password": "secret123",
  "use_sqlite": true
  }
```

If `use_sqlite` is set to `false`, the user is created in the connected MySQL database, THAT NEEDS TO ALREADY HAVE THE `users` TABLE CREATED CORRECTLY. This is kept only as backward compatibility with another personal system and is not the intended way to create or access users login.



### **GET /auth/me**

Returns information about the currently authenticated user.

Requires a valid JWT token in the `Authorization` header.

**Example response:**

```json
{
  "user_id": 1,
  "email": "john@example.com"
}
```



### **POST /auth/refresh**

Generates a new access token for the authenticated user without requiring re-login.



### Notes

- The authentication system is compatible with Laravel’s bcrypt password hashes.
    
    It automatically converts `$2y$` hashes (Laravel) to `$2b$` for Python verification.
    
- When disabled (`ENABLE_AUTHENTICATION=0`), all endpoints are publicly accessible.
- Tokens expire after the time defined in `JWT_TOKEN_EXPIRE_MINUTES`, after which a `/auth/refresh` request or re-login is required.