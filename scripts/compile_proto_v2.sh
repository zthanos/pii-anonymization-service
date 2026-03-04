#!/bin/bash

# Compile the V2 protobuf definitions

set -e

echo "Compiling protobuf V2 definitions..."

# Create output directory if it doesn't exist
mkdir -p src/pii_service/proto

# Compile the proto file
python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    src/pii_service/proto/pii_service_v2.proto

echo "✓ Protobuf V2 compilation complete"
echo "Generated files:"
echo "  - src/pii_service/proto/pii_service_v2_pb2.py"
echo "  - src/pii_service/proto/pii_service_v2_pb2_grpc.py"
