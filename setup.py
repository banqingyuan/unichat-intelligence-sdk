from setuptools import setup, find_packages

setup(
    name='unichat-prompt-sdk',
    version='0.0.5',
    packages=find_packages(),
    package_data={"unichat-prompt-sdk": ["prompt_factory/tpl/*.yml"]},
    include_package_data=True,
    install_requires=[
        'pydantic==1.10.9',
        'redis==4.5.5',
        'aioredis==2.0.1',
        'openai==0.27.8',
        'setuptools==68.0.0',
        'pinecone-client==2.2.1',
        'numpy==1.24.4',
        'PyYAML==6.0'
    ]
)
