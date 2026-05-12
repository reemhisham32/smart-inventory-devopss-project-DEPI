# 📦 Smart Inventory App — DevOps Project (DEPI)
<img width="1600" height="765" alt="WhatsApp Image 2026-05-12 at 1 26 10 PM" src="https://github.com/user-attachments/assets/340e9120-4970-4121-b404-cdeddaf2199c" />


A full-stack inventory management web application built with **Flask** and deployed on **AWS EKS** using a complete CI/CD pipeline powered by **Jenkins**, **Docker**, and **ArgoCD**.

---

## 🏗️ Project Structure

```
smart-inventory-devopss-project-DEPI/
├── app/
│   ├── app.py              # Flask application (REST API + UI)
│   ├── requirements.txt    # Python dependencies
│   └── templates/
│       └── index.html      # Frontend UI
├── k8s/
│   ├── deployment.yaml     # Kubernetes Deployment (2 replicas)
│   └── service.yaml        # Kubernetes Service (LoadBalancer)
├── argocd/
│   └── application.yaml    # ArgoCD Application (GitOps)
├── Dockerfile              # Container image definition
└── Jenkinsfile             # CI/CD pipeline definition
```

---

## ✨ Features

- **Product Management** — Add, update, delete, and search products
- **Category Filtering** — Filter products by category
- **Inventory Stats** — Total products, total stock, low-stock alerts, inventory value
- **Health Check Endpoint** — `/health` for Kubernetes readiness & liveness probes
- **Auto-seeded Demo Data** — Pre-populated data on first run

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, Flask 3.0, Flask-SQLAlchemy |
| Database | SQLite |
| Container | Docker (python:3.11-slim) |
| CI/CD | Jenkins |
| Registry | Docker Hub |
| Orchestration | Kubernetes (AWS EKS) |
| GitOps | ArgoCD + ArgoCD Image Updater |
| Infrastructure | Terraform (see infra repo) |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve the frontend UI |
| `GET` | `/api/products` | List all products (supports `?search=` and `?category=`) |
| `GET` | `/api/products/<id>` | Get a single product |
| `POST` | `/api/products` | Create a new product |
| `PUT` | `/api/products/<id>` | Update a product |
| `DELETE` | `/api/products/<id>` | Delete a product |
| `GET` | `/api/stats` | Get inventory statistics |
| `GET` | `/health` | Health check |

---

## 🚀 Running Locally

### Prerequisites
- Python 3.11+
- Docker (optional)

### Run with Python

```bash
cd app
pip install -r requirements.txt
python app.py
```

App will be available at: `http://localhost:5000`

### Run with Docker

```bash
docker build -t smart-inventory-app .
docker run -p 5000:5000 smart-inventory-app
```

---

## ⚙️ CI/CD Pipeline (Jenkinsfile)

The Jenkins pipeline runs the following stages automatically:

1. **Checkout Code** — Pull latest code from GitHub
2. **Docker Login** — Authenticate with Docker Hub using stored credentials
3. **Build Docker Image** — Build and tag image as `reemhisham32/smart-inventory-app:<BUILD_NUMBER>`
4. **Push to Docker Hub** — Push both versioned and `latest` tags
5. **Update Kubeconfig** — Connect Jenkins agent to the EKS cluster
6. **Deploy to EKS** — Apply K8s manifests and rolling-update the image
7. **Verify Deployment** — Check pods and service status

### Required Jenkins Credentials
- `dockerhub-creds` — Docker Hub username & password

### Environment Variables
```
AWS_DEFAULT_REGION = us-east-1
EKS_CLUSTER_NAME   = my-eks-project-dev-cluster
DOCKERHUB_USERNAME = reemhisham32
IMAGE_NAME         = smart-inventory-app
```

---

## 🔄 GitOps with ArgoCD

The `argocd/application.yaml` configures ArgoCD to:

- **Watch** the `k8s/` directory in this repository
- **Auto-sync** changes to the `default` namespace on the EKS cluster
- **Self-heal** if manual changes are made to the cluster
- **Prune** removed resources automatically

### ArgoCD Image Updater
ArgoCD Image Updater automatically detects new Docker Hub images and updates the deployment without manual intervention, using the `newest-build` strategy.

---

## ☸️ Kubernetes Manifests

### Deployment (`k8s/deployment.yaml`)
- **2 replicas** for high availability
- Image: `reemhisham32/smart-inventory-app:latest`
- **Readiness Probe**: `GET /health` — starts routing traffic after 10s
- **Liveness Probe**: `GET /health` — restarts pod if unhealthy after 20s

### Service (`k8s/service.yaml`)
- Type: `LoadBalancer` — exposes the app publicly via AWS ELB
- External port `80` → Container port `5000`

---

## 🔗 Related Repository

Infrastructure provisioned with Terraform:  
👉 [smart-inventory-infra-terraform-DEP](https://github.com/reemhisham32/smart-inventory-infra-terraform-DEP)

