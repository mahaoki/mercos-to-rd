version: "3.9"

networks:
  web:
    external: false

services:
  reverse-proxy:
    image: traefik:v3.0
    container_name: traefik
    command:
      - "--api.dashboard=false"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      # Entrypoints HTTP/HTTPS
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      # Redireciona HTTP -> HTTPS
      - "--entrypoints.web.http.redirections.entryPoint.to=websecure"
      - "--entrypoints.web.http.redirections.entryPoint.scheme=https"
      # Let's Encrypt (HTTP-01)
      - "--certificatesresolvers.le.acme.email=${TRAEFIK_ACME_EMAIL}"
      - "--certificatesresolvers.le.acme.storage=/letsencrypt/acme.json"
      - "--certificatesresolvers.le.acme.httpchallenge.entrypoint=web"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "./letsencrypt:/letsencrypt"
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
    restart: unless-stopped
    networks:
      - web

  mercos-rd:
    build: .
    container_name: mercos-rd
    env_file:
      - .env
    expose:
      - "8000"
    labels:
      - "traefik.enable=true"
      # Roteamento por Host
      - "traefik.http.routers.mercos-rd.rule=Host(`${DOMAIN}`)"
      - "traefik.http.routers.mercos-rd.entrypoints=websecure"
      - "traefik.http.routers.mercos-rd.tls.certresolver=le"
      # Serviço aponta para porta interna 8000 do container
      - "traefik.http.services.mercos-rd.loadbalancer.server.port=8000"
    depends_on:
      - reverse-proxy
    restart: unless-stopped
    networks:
      - web
