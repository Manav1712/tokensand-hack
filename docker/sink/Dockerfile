FROM alpine:3.22
RUN apk add --no-cache dnsmasq python3
COPY entrypoint.sh /entrypoint.sh
COPY http_catchall.py /http_catchall.py
RUN chmod +x /entrypoint.sh /http_catchall.py
ENTRYPOINT ["/entrypoint.sh"]
