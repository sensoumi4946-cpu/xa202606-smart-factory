# OPC UA certificates

Place the site-issued files here before installation:

- `client-cert.pem`: XA-202606 client certificate
- `client-key.pem`: matching private key; mode `0640`, owned by `root:xa202606`
- `server-cert.pem`: pinned certificate of the OPC UA server
- `server-key.pem`: matching OPC UA gateway private key; mode `0640`

Do not commit real private keys. The installer copies this directory only when
the files exist. Development without OPC UA may leave it empty.
