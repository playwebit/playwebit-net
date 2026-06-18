from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name             = "playweb-node",
    version          = "1.0.0",
    author           = "PlayWebIT",
    description      = "PlayWebit Network — L1 blockchain SDK",
    long_description = long_description,
    long_description_content_type = "text/markdown",
    url              = "https://github.com/playwebit/playwebit-net",
    packages         = find_packages(),
    python_requires  = ">=3.10",

    install_requires = [
        "flask>=2.3.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "apscheduler>=3.10.0",
    ],

    extras_require = {
        # Signature verification (recommended)
        "eth":      ["eth-account>=0.10.0"],
        # Storage backends (install what you need)
        "leveldb":  ["plyvel>=1.5.0"],
        "supabase": ["supabase>=2.0.0"],
        # Everything
        "all": [
            "eth-account>=0.10.0",
            "plyvel>=1.5.0",
            "supabase>=2.0.0",
        ],
    },

    classifiers = [
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
