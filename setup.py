from setuptools import setup, find_packages

setup(
    name='unichat-prompt-sdk',
    version='0.0.1',
    packages=find_packages(),
    package_data={"unichat-prompt-sdk": ["*.pyi"]},
    include_package_data=True,
    install_requires=[
        'pydantic==1.10.9',
        'redis==4.5.5',
        'aioredis==2.0.1',
        'openai==0.27.8',
        'setuptools==68.0.0',
        'pinecone-client[grpc]==2.2.2',
        'numpy==1.25.0',
    ]
)
