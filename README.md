# Home Automation Simulation Server

## Overview

This application runs a FastAPI-based server that simulates home automation based on appliance usage and power thresholds. It utilizes an SQLite database for storing consumption data and configuration settings.

## Running the Application

To start the application, execute the following command:

```sh
python.exe server.pyc
```

## Directory Structure

```
├── server.pyc           # Compiled FastAPI server script
├── data/                # Contains database and configuration files
│   ├── digital_twin_consumption.db  # SQLite database storing device power and duration 
│   ├── digital_twin_consumption.db   # SQLite database storing  house configuration (maximum power, energy cost...)
│   ├── configuration.txt # INI-style configuration file
```

## Configuration

The **configuration.txt** file follows an INI-like format and allows you to configure the following settings:

### **Home Assistant API Settings:**

- `server_url`: The URL of the Home Assistant API. It's the full url also considering the /api part.
- `token`: The authentication token for API access.

### **Server Settings:**

- `host`: The host URL for running the FastAPI server.
- `port`: The port number on which the server listens.

## Requirements
The application depends on various Python packages, which are listed in the **requirements.txt** file. Before running the application, ensure all dependencies are installed by executing the following command:
```sh
pip install -r requirements.txt
```
This will install all required packages, including FastAPI, Uvicorn, and any additional dependencies necessary for the server to function properly.


