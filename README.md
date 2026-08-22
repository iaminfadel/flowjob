# Amin Fadel — Robotics & Embedded Software Engineer

**Cairo, Egypt** · aminmoustafa.f@gmail.com · [LinkedIn](https://www.linkedin.com/in/amin-fadel-595313161) · [GitHub](https://github.com/iaminfadel)
Military Service: Exempted · Available full-time

---

Mechatronics & Robotics Engineering graduate (Honors, GPA 3.84/4.0, Class Rank 1st) with hands-on experience in space robotics, autonomous navigation, and AI. Led the software team and served as Mission Leader for Ain Shams University's space robotics team (ASU ROAR) at the European Rover Challenge, certified by the European Space Foundation. Built and tested perception, navigation, and control software for rovers and autonomous vehicles.

---

## Education

**Ain Shams University** — BSc. Mechatronics and Robotics Engineering, *With Honors*
Cairo, Egypt · Sep 2021 – Jul 2026 · GPA 3.84/4.0 — Class Rank: 1st

## Experience

**Honda Research Institute (HRI) × ASU ROAR** — AI Assistant Integration, Research Collaboration
*Remote / Cairo, Egypt · Feb 2026 – Present*
- Point of contact for HVoice, an experimental AI task-management assistant by Honda Research Institute
- Authored the task specification defining HVoice's role and workflow integration

**Morganz Integrated Solutions** — Full-Stack IoT Software Engineer (Part-Time)
*Cairo, Egypt · Jun 2026 – Aug 2026*
- Production ESP32-S3 firmware (ESP-IDF): MQTT-over-TLS, OTA with rollback, BLE provisioning
- Built the Node.js/Express API gateway over ThingsBoard; contributed React Native app + Playwright e2e

**Sparrow — Smart Agriculture Systems** — Embedded Software Engineer (Part-Time)
*Cairo, Egypt · Apr 2025 – Apr 2026*
- Owned full embedded lifecycle for STM32 irrigation controller in Embedded C
- GitHub Actions CI/CD for automated builds and tests

**ASU ROAR — European Rover Challenge** — Mission Leader & Software Team Leader
*Cairo, Egypt · Nov 2024 – Sep 2025*
- Led 10-person software team to 21st place at ERC, owning system architecture in ROS
- Directed perception: YOLO 3D detection, TensorRT inference, RANSAC point-cloud obstacles
- Certified by the European Space Foundation (Senior System Engineer, Head of Software, Head of Control, Mission Leader)

**ASU Racing Team — Formula Student AI UK** — Formula AI Team Vice Captain
*Cairo, Egypt · Aug 2022 – Aug 2024*
- FastSLAM pipeline in Python with LiDAR SLAM (LeGO-LOAM), Hungarian data association
- 5th place finish; cut raceline computation 151s → 17s (~90%)
- IPG CarMaker + custom ROS2 interface for full-system testing

**ARL, Ain Shams University** — Autonomous Vehicles Workshop Instructor
*Cairo, Egypt · Aug 2023 – Oct 2023*
- Taught control theory, mentored PID design on physical robots in ROS

**MATGR For Engineering and Trading** — Powertrain Intern
*Cairo, Egypt · Aug 2023 – Sep 2023*
- Motor controllers, BMS, wire harness diagrams, electrical schematics for EV golf carts

## Selected Projects

- **FlowJob** *(2026 – Present)* — open-source multi-agent AI pipeline that scouts jobs, scores fit, tailors resumes, and applies via LinkedIn Easy Apply with an approval gate
- **Advanced PMSM Control & Testing Platform for EVs** *(2025 – Present)* — MATLAB/Simulink FOC with MIL/HIL on NI myRIO; ISO 26262 / IEC 61508 safety layer
- **LLM-Based Autonomous Robot Control System** *(2024)* — GPT-3 + ROS natural-language robot control in CoppeliaSim
- **ML Optimized Smart Traffic System** *(2024)* — DQN RL agent, −35–50% queue length, −40% delay
- **Lane Tracking System — Machathon 5.0 (2nd Place)** *(2024)* — OpenCV lane detection pipeline
- **5-DOF Robotic Arm** *(2023)* — 300 Hz cascaded PID, ESP32, 5° accuracy
- **CoreXY 3D Printer** *(2024 – Present)* — custom high-speed motion control build

## Certificates & Awards

- **2026** — 1st Place, Global HackAtom Egypt (Rosatom & NPPA)
- **2025** — Senior System Engineer | Head of Software | Head of Control | Mission Leader, ERC 2025 (European Space Foundation)
- **2025** — 1st Place, AI Competition, Ain Shams University Faculty of Engineering
- **2024** — 2nd Place, Machathon 5.0 Autonomous Vehicle Challenge
- **2023** — 5th Place, Formula Student AI UK, IMechE

## Technical Skills

- **Robotics & Autonomy** — ROS/ROS2, Autonomous Navigation, Sensor Fusion, LiDAR SLAM, Point Cloud Processing, Estimation Filters
- **Perception & AI** — Computer Vision, OpenCV, PCL, TensorFlow, TensorRT, Deep Q-Networks, Camera Systems
- **Control Systems** — PID, MPC, Field-Oriented Control (FOC), SVPWM, Model-Based Design, Hardware-in-the-Loop (HIL)
- **Embedded Systems** — Embedded C, C++, STM32, ESP32, ESP8266, RP2040, FreeRTOS, NI myRIO, SPI, I2C, UART
- **Simulation & Tools** — MATLAB/Simulink, Simulink Embedded Coder, Simscape, CoppeliaSim, IPG CarMaker, Proteus
- **DevOps & Research** — Git, GitHub Actions, CI/CD, Docker, Linux, Technical Documentation
- **Languages** — Arabic (Native), English (Fluent)

---

# FlowJob

The engine behind the CV above — an agentic job-application pipeline that scouts LinkedIn for jobs, scores fit, tailors a resume per job, evidences gaps via grilling, and applies through LinkedIn Easy Apply. All from one SQLite database and one config file.

> The full machine-readable version of the CV above lives in [`master_resume.md`](master_resume.md) — the single source of truth the Tailor agent parses for every application.

## Features

- Deterministic pipeline: scout → analyst → tailor → editor → critic/writer
  (evidence loop) → approval gate → applicator, with per-stage retry states
- Human-in-the-loop seams: approval gate before applying, grilling sessions for
  missing-evidence gaps, pause-on-unknown-form-field during Easy Apply
- **Cockpit TUI** (`flowjob tui`) — full-screen Textual front door: dashboard,
  job browser, LLM log viewer, settings editor, and in-TUI watch hosting
- Watch mode: continuous cycles with jittered countdowns, lockfile-guarded so
  CLI and TUI watchers never run concurrently

## Quickstart

```bash
uv sync
uv run playwright install chromium
uv run flowjob validate          # parse master_resume.md, validate config, init DB
uv run flowjob login             # authenticate with LinkedIn (saves browser state)
uv run flowjob tui               # launch the cockpit
```

## Commands

| Command | Description |
| --- | --- |
| `flowjob validate` | Parse `master_resume.md`, validate `flowjob.yaml`, init the DB |
| `flowjob login` | Headed browser to authenticate with LinkedIn and save state |
| `flowjob run` | Run the pipeline once |
| `flowjob watch` | Run the pipeline continuously with jittered countdowns |
| `flowjob tui` | Launch the cockpit TUI |
| `flowjob status` | DB summary counts + last successful cycle timestamp |
| `flowjob add` | Log a manual application |
| `flowjob update <id> --state X` | Flip any job's state (e.g. `REJECTED`) |
| `flowjob audit-bank` | Audit the master resume bullet bank |
| `flowjob grill` | Start or resume a grilling session for a job needing evidence |
| `flowjob logs` | Browse persisted LLM request/response logs |
