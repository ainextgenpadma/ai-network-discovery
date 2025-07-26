# ai-network-discovery
Automated Cisco Network Inventory with Connected Device Insights

**Overview**
This project uses an AI-assisted Python script to automatically:
Discover Cisco switch stack sizes and models
Identify all connected end devices using LLDP neighbor info
Lookup MAC vendors using OUI mapping
Generate structured Excel reports
Provide full logs for troubleshooting and planning
The solution was developed with help from ChatGPT, accelerating development and bypassing the need for expensive network management platforms.

**Objective**
Feature	Description
🧠 AI-assisted scripting	All logic was developed via prompt engineering using ChatGPT
🔗 SSH-based Discovery	Connects to switches using Netmiko
📦 Stack Size Detection	Parses show switch to get number of stack members
🛠️ Switch Model Parsing	Uses show inventory and filters out non-switch modules
🔌 LLDP Neighbor Discovery	Parses show lldp neighbors detail to find connected devices
🧬 MAC Address + Vendor Lookup	Extracts MACs and identifies vendors using OUI prefix
📊 Structured Reporting	Outputs data into an Excel sheet: switch_report.xlsx
🪵 Logging & Fault Tolerance	Full log file and exception handling per switch

**How It Works**
Reads input from switch_list.xlsx with the following columns:
hostname
ip
username
password
SSHes into each Cisco switch using Netmiko.

**Executes**:

This script is a real example of AI-powered assistance:
Entire code logic (Netmiko setup, LLDP parsing, vendor lookup) was co-written with ChatGPT
Iteratively refined the script to support new features like LLDP, MAC filtering, and vendor mapping
Delivered a scalable automation tool in hours, not days
Replaced the need for expensive NMS tools like Cisco Prime, SolarWinds, or Aruba AirWave

📁 Files
**File Name	Description**
network_discovery.py	Main script (shown above)
switch_list.xlsx	Input file (your switch inventory with credentials)
switch_report.xlsx	Auto-generated report with stack data
switch_discovery.log	Log file capturing connection status/errors
README.md	This documentation
