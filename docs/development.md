# Development

Use Python 3.12 or newer and install the development extras:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[cli,serial,dev]"
```

For USB camera perception, install the optional extra and obtain YuNet
explicitly:

```bash
pip install -e ".[perception]"
sirah-models yunet --destination models/yunet
```

The model is checksum-verified and ignored by Git. Do not make runtime startup
download models or require a camera in CI.
