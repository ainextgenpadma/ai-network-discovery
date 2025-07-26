**AI-Assisted Device Inventory Snapshot**
Automated Network Discovery using Cisco CLI, LLDP, ARP, and MAC OUI

**Overview**
This project automates the creation of a comprehensive snapshot of all network-connected devices per switch — including MAC addresses, LLDP neighbors, vendor lookup via OUI, and last traffic timestamps.
The Python script was developed using ChatGPT as a coding assistant, allowing rapid iteration, efficient parsing logic, and robust error handling. It stores all output in both SQLite and Excel formats.

🎯 What It Does
**Feature	Description**
🧠 AI-Assisted Scripting	Script was co-developed using ChatGPT
🔗 SSH-based CLI Discovery	Uses Netmiko to connect to Cisco IOS switches
📊 Interface Status Parsing	Parses show interfaces status for port status, VLAN, etc.
🔌 MAC Address Table	Extracts MAC addresses from show mac address-table
🧬 OUI → Vendor Lookup	Queries MAC vendors via cached OUI or external API
🧭 LLDP Neighbor Details	Parses show lldp neighbors detail for topology mapping
🕒 Last Traffic Seen	Extracts last input/output from show interfaces
🌐 ARP IP Mapping	Matches MAC to IP using L3 switch ARP table
💾 Multi-format Output	Appends data to:

device_inventory.db (SQLite)
device_inventory.xlsx (new sheet per day)

📁 Input File: switch_list.xlsx
Column	Description
switch_type	access_switch or layer3_switch
ip	Management IP of the switch
username	SSH username
password	SSH password

📂 **Output**
device_inventory.xlsx
New sheet created for each run (e.g., 2025-07-26)

Each row corresponds to one switch port

device_inventory.db
Append-only log of inventory snapshots

**Enables historical tracking and queries**

**Sample Columns:**
switch_name	port	status	vlan	mac_address	vendor	neighbor_name	ip_address	last_traffic_seen

**🛠️ How to Use**
✅ Install Requirements
bash
Copy
Edit
pip install pandas openpyxl netmiko requests

**▶️ Run the Script**
bash
Copy
Edit
python device_inventory.py

**🔒 Notes**
Cisco IOS switches are required for CLI compatibility
LLDP, ARP, and MAC address table parsing works best with consistent CLI outputs
The OUI vendor cache (oui_cache.csv) will be created automatically
Logging output is written to device_inventory.log

**📌 Why This Project Matters**

Replaces expensive network discovery tools like Cisco Prime or SolarWinds
Provides rich, real-time network visibility
Enables data-driven planning for migrations, cleanups, and capacity analysis
Built in collaboration with an AI assistant, reducing manual effort

**📬 Contact**
Padma Chandran
linkedin.com/in/padmachandran07

