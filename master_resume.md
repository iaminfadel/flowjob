---
# ==============================================================================
# FLOWJOB MASTER RESUME SCHEMA
# ==============================================================================
# This is the single source of truth for your professional history.
# The Tailor agent will parse this file and extract only the relevant pieces
# to generate a targeted CV for each job application.
# ==============================================================================

# 1. PERSONAL DETAILS
name: "Amin Fadel"
full_name: "Amin Moustafa Fadel"
title: "Robotics & Embedded Software Engineer"
email: "aminmoustafa.f@gmail.com"
phone: "+201001681969"
location: "Cairo, Egypt"
nationality: "Egyptian"
military_service: "Exempted"
availability: "Available full-time"

# 2. LINKS
links:
  - name: "LinkedIn"
    url: "https://www.linkedin.com/in/amin-fadel-595313161"
  - name: "GitHub"
    url: "https://github.com/iaminfadel"

# 2b. LANGUAGES SPOKEN (rendered as the final Technical Skills line)
languages_spoken: ["Arabic (Native)", "English (Fluent)"]

# 2c. CERTIFICATES & AWARDS (rendered as their own section; most recent first)
certificates_awards:
  - year: "2026"
    title: "1st Place, Global HackAtom Egypt (Rosatom & NPPA)"
  - year: "2025"
    title: "Senior System Engineer | Head of Software | Head of Control | Mission Leader, ERC 2025 (European Space Foundation)"
  - year: "2025"
    title: "1st Place, AI Competition, Ain Shams University Faculty of Engineering"
  - year: "2024"
    title: "2nd Place, Machathon 5.0 Autonomous Vehicle Challenge"
  - year: "2024"
    title: "Innovation and Entrepreneurship Training, InnovEgypt (TIEC)"
  - year: "2024"
    title: "Embedded Systems Intermediate, AMIT / Orange Digital Center"
  - year: "2023"
    title: "5th Place, Formula Student AI UK, IMechE"

# 2d. GRADUATION PROJECT (rendered as its own section when relevant)
graduation_project:
  title: "Advanced PMSM Control & Testing Platform for Electric Vehicles"
  url: "https://github.com/iaminfadel"
  date_range: "2025 -- 2026"
  highlights:
    - "Built a MATLAB/Simulink framework for EV motor control with Field-Oriented Control (FOC) and optimized PI gains; validated it with MIL and HIL tests on NI myRIO hardware."
    - "Automated embedded C code and calibration file generation with Simulink Embedded Coder; validated the XCP protocol for live parameter tuning."
    - "Designed a safety layer with fault detection, emergency shutdown, and thermal protection (ISO 26262 / IEC 61508 compliant); ran hardware-level unit tests on motor and sensor modules."

# 2e. PROFILE BASE (seed text for the tailored Profile section; Tailor adapts per JD)
profile_base: "Mechatronics & Robotics Engineering graduate (Honors, GPA 3.84/4.0, Class Rank 1st) with hands-on experience in space robotics, autonomous navigation, and AI. Led the software team and served as Mission Leader for Ain Shams University's space robotics team (ASU ROAR) at the European Rover Challenge, certified by the European Space Foundation."

# 3. SKILLS TAXONOMY
# Group skills logically so the Analyst agent can easily compute fit scores.
skills:
  languages: ["Embedded C", "C++", "Python", "MATLAB", "JavaScript/TypeScript", "SQL"]
  frameworks: ["ROS", "ROS2", "TensorFlow", "TensorRT", "OpenCV", "PCL", "FreeRTOS"]
  tools: ["Git", "GitHub Actions", "Docker", "Simulink Embedded Coder", "Simscape", "IPG CarMaker", "CoppeliaSim", "Siemens TIA Portal", "FactoryIO", "PrusaSlicer CLI", "Playwright", "Altium", "Proteus"]
  embedded_and_hardware: ["STM32", "ESP32", "ESP8266", "RP2040", "NI myRIO", "AVR", "PMSM", "BLDC", "Field-Oriented Control (FOC)", "SVPWM", "XCP Protocol", "A2L Calibration"]
  concepts: ["Autonomous Navigation", "FastSLAM", "LiDAR SLAM (LeGO-LOAM)", "Sensor Fusion", "Point Cloud Processing (RANSAC, Euclidean Clustering)", "Camera Intrinsic Projection", "Computer Vision (YOLO)", "Deep Q-Networks (RL)", "Model-Based Design", "Control Theory (PID, MPC)", "Kalman Filtering (EKF, Adaptive Fading EKF)", "Hardware-in-the-Loop (HIL)", "CI/CD", "Functional Safety (ISO 26262, IEC 61508)"]

# 4. PREFERENCES & TARGET ROLES
# This helps the Analyst agent filter out jobs that don't match your goals.
preferences:
  target_roles: ["Robotics Software Engineer", "Embedded Software Engineer", "ROS Developer", "Autonomous Systems Engineer", "Firmware Engineer", "Control Systems Engineer", "Mechatronics Engineer"]
  avoid_roles: ["BIM", "Technical Office", "Site Engineer", "Civil", "Architect", "Sales", "Marketing", "Teacher", "Instructor", "Intern", "Trainee"]
  work_types: ["Remote"]
  target_locations: ["Egypt"]
  min_salary_usd: null # Optional, set to null if not applicable

# 5. PERSONAL NUDGE / TONE (For AI Summary Generation)
# The Tailor agent will write a custom 2-3 sentence summary for each JD.
# Use this section to guide its tone and give it personal flavor to inject.
personal_nudge:
  tone: "Highly technical, results-oriented, precise, leadership-driven with deep domain authority in robotics, autonomous systems, and embedded firmware."
  key_themes: ["Autonomous vehicle & rover software leadership", "Production embedded firmware & real-time control", "High-performance perception & SLAM pipelines", "0 to 1 system architecture & CI/CD"]
  personal_flavor: "Passionate about autonomous rovers, race cars, low-level firmware optimization, and building AI agent workflows."

# 6. EDUCATION
education:
  - institution: "Ain Shams University"
    degree: "BSc. Mechatronics and Robotics Engineering"
    location: "Cairo, Egypt"
    start_date: "2021-09"
    end_date: "2026-07"
    gpa: "3.84/4.0 (Class Rank: 1st, Honors)"

---

# ==============================================================================
# EXPERIENCE NARRATIVES
# ==============================================================================
# Format:
# ## [Company] | [Role] | [Location] | [Start Date] - [End Date]
# 
# ### Context
# (Optional) A brief paragraph about the company/team to provide context.
#
# ### Achievements
# Write exhaustive bullet points here. Write EVERY achievement, even if it makes
# the resume 10 pages long. The Tailor agent will select the top 3-5 most 
# relevant bullets for each specific JD.
# 
# Tagging (Optional):
# You can append tags like [leadership], [scale], [python] to bullets to help 
# the Tailor agent pick the right ones.
# ==============================================================================

## Honda Research Institute (HRI) | AI Assistant Integration - Research Collaboration | Remote / Cairo, Egypt | 2026-02 - Present

### Context
Honda Research Institute conducts advanced research in robotics, artificial intelligence, and human-machine teaming. Collaborating directly with HRI developers to integrate and field-test an experimental AI management assistant designed for space robotics and rover competition workflows.

### Achievements
- Contributing domain expertise as rover team lead to the integration and field-testing of an experimental AI management tool developed by Honda Research Institute for space robotics teams. [robotics, ai, space-robotics, collaboration, research]
- Participating in regular meetings with HRI developers to provide structured feedback on rover team workflows and feature requirements from a practitioner's perspective. [feedback, requirements, product, agile]
- Authored the task specification document defining the assistant's operational context, user interaction boundaries, and integration touchpoints for the rover team use case. [specifications, documentation, system-design]
- Preparing deployment testing protocols and KPI evaluation metrics of the tool within the team's active competition workflow. [testing, kpi, evaluation, deployment]


## Morganz Integrated Solutions | Full-Stack IoT Software Engineer (Part-Time) | Cairo, Egypt | 2026-06 - 2026-08

### Context
Morganz Integrated Solutions builds agricultural IoT irrigation and field-monitoring systems. CyberFlow is the company's flagship platform: ESP32-based irrigation controllers, a ThingsBoard cloud backend, a custom API gateway, and a React Native app across iOS, Android, and Web.

### Achievements
- Developed production ESP32-S3 (ESP-IDF) firmware for the CyberFlow irrigation controller: MQTT-over-TLS telemetry and two-way RPC, hardware-adaptive PSRAM fallback, static MQTT buffer sizing, offline-resilient shared-attribute synchronization, and scheme-adaptive OTA verification with rollback on verified MQTT reconnection. [embedded-c, esp32, esp-idf, firmware, mqtt, ota, rtos]
- Implemented the device provisioning lifecycle with protocomm BLE onboarding (NimBLE, Security 1), factory pre-registration binding, and a dual-policy WiFi reconnection strategy balancing radio coexistence during setup with indefinite background reconnection in operational mode. [ble, provisioning, security, iot, networking]
- Built the custom Node.js/Express API gateway layer over ThingsBoard CE (Docker Compose on a single-node production host) with PostgreSQL/Prisma persistence, a unified ThingsBoard adapter seam for internal UUID resolution and auth-token retries, and atomic device claiming via factory pre-registration. [nodejs, express, thingsboard, postgres, prisma, rest-api]
- Contributed to the React Native (Expo) app across iOS, Android, and Web, migrating UI screens to a custom Stitch design system and establishing a Playwright visual-test pipeline for the web surface. [react-native, expo, typescript, ui, design-system]
- Authored extensive Playwright e2e suites covering settings persistence, telemetry filtering, OTA target validation, float sanitization, same-zone overrides, queue bursts, and hardware-offline RPC resilience; tracked physical-hardware regressions on a QA board. [playwright, e2e, testing, qa]
- Authored 11 architecture decision records (ADRs) documenting production-hardening choices: centralized state-sync boundary, pure telemetry normalizer seam, deep schedule module seam, static MQTT buffering, PSRAM fallback, and the offline provisioning lifecycle. [architecture, adr, system-design, documentation]


## Sparrow - Smart Agriculture Systems | Embedded Software Engineer (Part-Time) | Cairo, Egypt | 2025-04 - 2026-04

### Context
Sparrow develops smart agricultural automation systems, IoT telemetry, and embedded hardware for automated precision farming.

### Achievements
- Owned the complete embedded software lifecycle for an STM32-based automatic irrigation controller in production Embedded C — from authoring system requirements and designing firmware architecture through implementation, unit testing, and hardware deployment. [embedded-c, stm32, firmware, architecture, control]
- Built a comprehensive unit testing suite covering core control logic and peripheral interface modules, preventing regressions across hardware revisions. [unit-testing, embedded, c, quality, test-automation]
- Designed and deployed a CI/CD pipeline on GitHub Actions for automated compilation, test execution, and build artifact management across embedded targets. [cicd, github-actions, devops, automation]
- Designed and deployed the company's public-facing landing page, handling frontend development and production deployment end-to-end. [frontend, web-development, deployment]


## ASU ROAR - European Rover Challenge | High-Level Software Team Leader and Mission Leader | Cairo, Egypt | 2024-11 - 2025-09

### Context
Ain Shams University's autonomous space robotics team competing at the European Rover Challenge (ERC). Certified as Senior System Engineer, Head of Software, Head of Control, and Mission Leader by the European Space Foundation. Led software architecture and operations for ERC 2025.

### Achievements
- Led a 10-person autonomous software team to a 21st place finish at the European Rover Challenge by owning the complete high-level system architecture and coordinating end-to-end integration across perception, localization, path planning, control, supervisor, and GUI subsystems within a ROS framework. [ros, robotics, leadership, system-architecture, systems-engineering]
- Defined system-level interfaces, data flows, and module boundaries across all subsystems prior to delegation, ensuring coherent integration and clear ownership across the team. [architecture, modular-design, interfaces, system-design]
- Directed development of the full perception pipeline: YOLO-based 3D detection fused with depth camera data via camera intrinsic projection, TensorRT INT8/FP16 onboard inference, and transition from UV-disparity obstacle detection to a point cloud pipeline using RANSAC ground removal and Euclidean clustering. [perception, computer-vision, yolo, tensorrt, point-cloud, ransac, sensor-fusion, optimization]
- Owned integration and deployment of all software modules, personally ensuring reliable execution across simulation environments and real-world outdoor rover testing. [integration, field-testing, simulation, deployment, robotics]
- Maintained software quality and cross-team alignment by leading code reviews, managing CI/CD pipeline integration, and interfacing the software team with mechanical and electrical subsystems throughout all phases of competition preparation and deployment. [code-review, cicd, cross-functional, quality, team-leadership]


## ASU Racing Team - Formula Student AI UK | Formula AI Team Vice Captain | Cairo, Egypt | 2022-08 - 2024-08

### Context
ASU Racing Team autonomous racing division competing at Formula Student AI UK, engineering full-scale driverless race vehicles. Started as a navigation and simulation team member, later leading the Formula AI division.

### Achievements
- Led the Formula AI team's technical strategy and operations by coordinating development across navigation, perception, and control subsystems with 15+ team members to compete at Formula Student AI UK. [leadership, autonomous-vehicles, technical-strategy, team-management]
- Personally implemented a FastSLAM pipeline in Python integrated with odometry output from a LiDAR SLAM system (LeGO-LOAM), using the Hungarian algorithm for cone landmark data association across successive frames to build a consistent track map during racing. [slam, fastslam, lidar, lego-loam, python, data-association, algorithms]
- Accelerated team development workflows by establishing an IPG CarMaker simulation environment and developing a custom ROS2 interface for integrated system-level testing across all autonomous subsystems. [simulation, ipg-carmaker, ros2, integration, testing]
- Contributed to a 5th place finish at Formula Student AI UK by developing core navigation and simulation systems, including reducing global raceline trajectory computation time from 151 seconds to 17 seconds — approximately a 90% improvement. [optimization, algorithms, navigation, trajectory-optimization, performance]


## ARL - Autotronics Research Lab, Ain Shams University | Autonomous Vehicles Workshop Instructor | Cairo, Egypt | 2023-08 - 2023-10

### Context
Autotronics Research Lab (ARL) focuses on automotive electronics, connected mobility, and autonomous vehicle research and education at Ain Shams University.

### Achievements
- Taught system dynamics and control theory fundamentals for mobile robot applications to a cohort of undergraduate engineering students. [teaching, control-theory, system-dynamics, robotics]
- Supervised hands-on control system implementation projects in ROS-based autonomous navigation. [ros, autonomous-navigation, mentorship, practical-engineering]
- Mentored students through PID controller design, tuning, and system stability analysis on physical mobile robot platforms. [pid, control-systems, robotics, hardware]


## EVER, ASU Racing Team | Modeling and Testing Team Member | Cairo, Egypt | 2023-09 - 2023-11

### Context
Electric Vehicle division of ASU Racing Team focused on powertrain engineering, motor control modeling, and power electronics validation.

### Achievements
- Developed powertrain simulation models including BLDC motors and motor controllers using MATLAB Simulink and Simscape. [matlab, simulink, simscape, bldc, powertrain, modeling]
- Created simulation environments for testing and validating control strategies prior to hardware implementation on the electric vehicle platform. [simulation, validation, control-systems, electric-vehicles]


## MATGR For Engineering and Trading | Powertrain Intern | Cairo, Egypt | 2023-08 - 2023-09

### Context
Engineering enterprise specialized in electric utility platforms, golf cart conversion, and powertrain solutions.

### Achievements
- Gained hands-on experience with DC motor controllers and battery management system (BMS) components in electric golf cart platforms. [bms, motor-controllers, hardware, ev]
- Created wire harness diagrams and rebuilt full electrical system schematics for the platform. [schematics, electrical-design, wire-harness, cad]


# ==============================================================================
# PROJECTS
# ==============================================================================
# Format:
# ## [Project Name] | [Role] | [Dates] | [Link]
# ==============================================================================

## FlowJob | Creator & Lead Maintainer | 2026 - Present | https://github.com/iaminfadel/flowjob
- Designed and built an open-source, multi-agent AI pipeline that scouts jobs, scores fit, tailors a resume per job, evidences gaps, and applies via LinkedIn Easy Apply — a deterministic pipeline (scout → analyst → tailor → editor → critic/writer → applicator) with per-stage retry states and an approval gate before any application is submitted. [ai, python, agents, automation, system-design, pipeline]
- Engineered a human-in-the-loop evidence loop: a coverage critic audits each tailored draft against the job description, classifies unaddressed requirements, and routes plausible gaps to interactive grilling sessions that convert answers into STAR bullets committed back to the resume bank. [llm, multi-agent, hitl, prompt-engineering, ats]
- Implemented a full-screen Textual TUI cockpit with a job browser, LLM interaction log viewer, settings editor with guardrail bounds, and an in-TUI watch mode hosting the pipeline on jittered countdowns (lockfile-guarded against concurrent CLI runs). [tui, textual, python, cli, developer-tools]
- Built robust browser automation with Playwright for LinkedIn Easy Apply, including saved auth state, headed login flow, and pause-on-unknown-form-field handling. [playwright, browser-automation, web-scraping]


## Advanced PMSM Control and Testing Platform for Electric Vehicles | Lead Control & Embedded Engineer | 2025 - Present | https://github.com/iaminfadel
- Developed a model-based design framework in MATLAB/Simulink for EV PMSM control, implementing Field-Oriented Control (FOC) with PI gain optimization via the Jellyfish Search Algorithm metaheuristic, achieving fully operational MIL and HIL testbeds on NI myRIO hardware. [foc, pmsm, matlab, simulink, hil, metaheuristics, motor-control]
- Automated embedded C code generation, compiler optimization configuration, and A2L calibration file generation using Simulink Embedded Coder, enabling model-traceable firmware builds deployed directly to target hardware. [embedded-coder, embedded-c, a2l, code-generation, firmware]
- Integrated and validated firmware against the BSW (basic software) layer and tested XCP protocol implementation using measurement/calibration GUI tools for live parameter access and tuning on target hardware. [xcp, bsw, calibration, testing, automotive]
- Completed hardware-level unit tests for SVPWM output and sensor interface modules, verifying signal timing, accuracy, and fault behavior on the physical platform. [svpwm, unit-testing, hardware-testing, signal-timing]
- Designed an ISO 26262 and IEC 61508 compliant supervisory layer incorporating emergency shutdown logic, fault detection and handling modes, and thermal protection for functional safety compliance. [iso-26262, iec-61508, functional-safety, safety, supervisory-control]


## LLM-Based Autonomous Robot Control System | Project Lead & Developer | 2024 | https://github.com/iaminfadel
- Enabled natural language robot control by integrating GPT-3 with ROS for real-time autonomous navigation command generation in a CoppeliaSim simulation environment. [llm, gpt, ros, autonomous-navigation, coppeliasim, ai]
- Achieved successful task completion across diverse navigation scenarios by engineering prompts that process continuous sensor data including object detection results, distance, and bearing into structured LLM inputs. [prompt-engineering, sensor-fusion, ai, robotics]
- Demonstrated LLM application to continuous-world robotics by bridging discrete language model outputs with a real-time control loop for differential drive mobile robot navigation, parsing JSON control outputs directly to ROS messages. [robotics, control-loop, json, ros, real-time]


## Machine Learning Optimized Smart Traffic System | Lead Developer | 2024 | https://github.com/iaminfadel
- Demonstrated application of model-free reinforcement learning to a traffic control optimization problem with continuous state-action space representation. [reinforcement-learning, dqn, machine-learning, optimization]
- Reduced intersection queue length by 35-50% and average vehicle delay time by approximately 40% by training a Deep Q-Network (DQN) RL agent in a MATLAB simulation environment. [matlab, dqn, optimization, simulation, rl]


## Neural Network and Machine Learning Library from Scratch | Lead Developer | 2024 | https://github.com/iaminfadel
- Implemented a complete neural network training library from scratch in Python, including forward and backward propagation, gradient descent variants, and layer abstractions. [python, machine-learning, deep-learning, algorithms, math]
- Developed a Support Vector Machine classifier using the Sequential Minimal Optimization (SMO) algorithm for the optimization step. [svm, smo, optimization, algorithms]
- Conducted memory and performance analysis demonstrating 28% better memory efficiency compared to an equivalent TensorFlow baseline implementation. [benchmarking, performance, optimization, memory-efficiency]


## Comparison of Real-Time Parameter Estimation Methods for Dynamic Systems | Researcher | 2024 | https://github.com/iaminfadel
- Investigated real-time parameter estimation for a DC motor-driven linear cart system by implementing and benchmarking three approaches: autoregressive ARX/ARMAX models, Extended Kalman Filter (EKF), and Adaptive Fading EKF. [kalman-filter, ekf, parameter-estimation, system-identification, state-estimation]
- Analyzed trade-offs between estimation accuracy, convergence speed, and robustness to noise across all three methods under varying operating conditions. [matlab, benchmarking, dynamic-systems, noise-filtering]


## Lane Tracking System - Machathon 5.0 (2nd Place) | Lead Computer Vision Developer | 2024 | https://github.com/iaminfadel
- Implemented a real-time lane detection and tracking pipeline using OpenCV for a competitive autonomous vehicle challenge, processing raw camera frames through color masking, edge detection, and Hough transform-based lane fitting. [opencv, computer-vision, lane-tracking, autonomous-vehicles, edge-detection]


## Hydroponic Control System | Embedded & Systems Engineer | 2023 - 2024 | https://github.com/iaminfadel
- Automated plant nutrition management by designing a multi-sensor feedback control system integrating pH, electrical conductivity (EC), and ultrasonic water level sensors. [embedded, sensors, control-systems, iot, feedback-control]
- Designed reliable embedded control by implementing FreeRTOS task scheduling algorithms on an RP2040 microcontroller, carrying the system from Simscape modeling through full hardware deployment. [freertos, rp2040, simscape, embedded-c, rtos]


## 5-DOF Robotic Arm Simulation and Control System | Control & Embedded Engineer | 2023 | https://github.com/iaminfadel
- Achieved 5-degree positioning accuracy across all joints by engineering a 300Hz cascaded PID controller with quadrature encoder feedback running on an ESP32 microcontroller. [esp32, pid, robotics, motion-control, embedded, feedback-control]
- Accelerated embedded deployment by leveraging Simulink automatic C code generation for embedded targets, reducing manual firmware development time. [simulink, code-generation, embedded-c, firmware]


## Automated 3D Slicing and BOM Generator | DevOps / Automation Engineer | 2023 | https://github.com/iaminfadel
- Built a custom GitHub Actions CI/CD pipeline that automatically converts Inventor .ipt files to .step format, slices them using PrusaSlicer CLI, and generates a full bill of materials for all 3D printed parts including material weight, support weight, volume, print settings, and estimated cost per part. [github-actions, cicd, automation, cad, prusaslicer, devops]
- Used the pipeline to fully automate and version-control the 3D printing process for the 5-DOF robotic arm project, enabling reproducible and trackable part manufacturing across design iterations. [manufacturing, automation, devops, 3d-printing]


## IoT-Enabled Rotary Gas Flowmeter | Embedded & IoT Engineer | 2023 | https://github.com/iaminfadel
- Achieved accurate volumetric flow measurement by implementing linear calibration via gain and bias estimation from experimental data on an ESP8266-based embedded system. [esp8266, iot, calibration, embedded, telemetry]
- Improved signal quality by applying low-pass and moving average filters in combination to reduce sensor noise from the hall-effect flow sensor. [dsp, signal-processing, filtering, noise-reduction]
- Enabled real-time remote monitoring by integrating pressure, temperature, and hall-effect sensors with Firebase cloud connectivity for live data streaming and logging. [firebase, cloud, iot, telemetry]


## PLC-Controlled Production Line with HMI | Automation Engineer | 2023 | https://github.com/iaminfadel
- Designed and simulated an automated production line using Siemens TIA Portal for PLC logic and FactoryIO for 3D simulation environment. [plc, tia-portal, factoryio, automation, simulation]
- Developed an HMI interface supporting operator control, real-time status monitoring, and production statistics display. [hmi, scada, industrial-automation]


## CoreXY 3D Printer | Hardware & Motion Control Lead | 2024 - Present | https://github.com/iaminfadel
- Designing and building a custom CoreXY 3D printer with focus on high-speed, high-precision motion. [corexy, 3d-printing, hardware, kinematics]
- Implementing the motion control system using linear rails, GT2 belt drive, and stepper motor control with tuned acceleration profiles. [motion-control, kinematics, stepper-motor, hardware-design]
