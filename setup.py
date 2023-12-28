from setuptools import setup, find_packages

setup(
    name='unichat-intelligence-sdk',
    version='0.3.65',
    packages=find_packages(),
    package_data={"unichat-intelligence-sdk": ["prompt_factory/tpl/*.yml"]},
    include_package_data=True,  # 这是关键：确保包含MANIFEST.in中指定的所有文件
    install_requires=[
        'pydantic==1.10.9',
        'redis==4.5.5',
        'aioredis==2.0.1',
        'setuptools==68.0.0',
        'numpy==1.24.4',
        'PyYAML==6.0',
        'SQLAlchemy==2.0.17'
    ]
)
