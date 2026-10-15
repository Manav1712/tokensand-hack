FROM alpine:3.20
RUN apk add --no-cache strace curl bash tar
RUN adduser -D -u 10001 agent
COPY run-phase.sh /warden/run-phase.sh
RUN chmod +x /warden/run-phase.sh
CMD ["sleep", "infinity"]
