import 'dart:io';
import 'dart:typed_data';

/// Find a checkout without assuming a developer's username or mount point.
String engineCheckoutRoot() {
  final configured = Platform.environment['NVFKU_ENGINE'];
  if (configured != null && configured.isNotEmpty) {
    if (!Directory('$configured/engine/nvfku').existsSync()) {
      throw StateError('NVFKU_ENGINE is not an engine checkout: $configured');
    }
    return configured;
  }
  var directory = Directory.current.absolute;
  while (true) {
    if (Directory('${directory.path}/engine/nvfku').existsSync()) {
      return directory.path;
    }
    final parent = directory.parent;
    if (parent.path == directory.path) {
      throw StateError('Run engine integration tests from inside the checkout');
    }
    directory = parent;
  }
}

/// A parseable AMD64 PE with one import; never a runnable game executable.
Uint8List minimalGamePe({String importedDll = 'd3d12.dll'}) {
  const peOffset = 0x40;
  const optionalOffset = peOffset + 24;
  const optionalSize = 0xf0;
  const sectionOffset = optionalOffset + optionalSize;
  const sectionRaw = 0x200;
  const sectionRva = 0x1000;
  const descriptorSize = 40; // One import descriptor and its zero terminator.
  final name = [...importedDll.codeUnits, 0];
  final sectionSize = descriptorSize + name.length;
  final bytes = Uint8List(sectionRaw + sectionSize);
  final data = ByteData.sublistView(bytes);
  bytes.setRange(0, 2, [0x4d, 0x5a]); // MZ
  data.setUint32(0x3c, peOffset, Endian.little);
  bytes.setRange(peOffset, peOffset + 4, [0x50, 0x45, 0, 0]);
  data.setUint16(peOffset + 4, 0x8664, Endian.little);
  data.setUint16(peOffset + 6, 1, Endian.little);
  data.setUint16(peOffset + 20, optionalSize, Endian.little);
  data.setUint16(peOffset + 22, 0x22, Endian.little);
  data.setUint16(optionalOffset, 0x20b, Endian.little);
  data.setUint32(optionalOffset + 120, sectionRva, Endian.little);
  data.setUint32(optionalOffset + 124, descriptorSize, Endian.little);
  bytes.setRange(sectionOffset, sectionOffset + 8, '.rdata\x00\x00'.codeUnits);
  data.setUint32(sectionOffset + 8, sectionSize, Endian.little);
  data.setUint32(sectionOffset + 12, sectionRva, Endian.little);
  data.setUint32(sectionOffset + 16, sectionSize, Endian.little);
  data.setUint32(sectionOffset + 20, sectionRaw, Endian.little);
  data.setUint32(sectionRaw + 12, sectionRva + descriptorSize, Endian.little);
  bytes.setRange(sectionRaw + descriptorSize, bytes.length, name);
  return bytes;
}
