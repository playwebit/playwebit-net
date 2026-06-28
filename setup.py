from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name             = "playweb-node",
    version          = "1.0.2",
    author           = "PlayWebIT",
    author_email     = "playwebit@gmail.com",
    description      = "PlayWebit Network — L1 blockchain SDK",
    long_description = long_description,
    long_description_content_type = "text/markdown",
    url              = "https://github.com/playwebit/playwebit-net",
    license          = "Apache-2.0",
    packages         = find_packages(),
    python_requires  = ">=3.10",

    install_requires = [
        "flask",
        "requests",
        "python-dotenv",
        "apscheduler",
    ],

    extras_require = {
        # Signature verification (recommended)
        "eth":      ["eth-account"],
        # Storage backends (install what you need)
        "leveldb":  ["plyvel"],
        "supabase": ["supabase"],
        # Everything
        "all": [
            "eth-account",
            "plyvel",
            "supabase",
        ],
    },

    classifiers = [
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache-2.0",
        "Operating System :: OS Independent",
    ],
)
