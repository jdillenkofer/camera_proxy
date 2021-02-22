-- This is a Wireshark dissector for the Baichuan/Reolink proprietary IP camera protocol.
-- Copy/symlink it into ~/.local/lib/wireshark/plugins/ and restart Wireshark;
-- You can use this to dissect the udp traffic from the camera.
-- Just add the random udp port to the DissectorTable.get("udp.port"):add call at the end.


-- @Note this dissector is incomplete and does not handle fragmented udp packets correctly.
bc_protocol = Proto("Baichuan",  "Baichuan/Reolink IP Camera Protocol")

udp_message_id = ProtoField.int8("baichuan.udp_message_id", "udp_message_id", base.DEC)
udp_connection_id = ProtoField.int32("baichuan.udp_connection_id", "udp_connection_id", base.DEC)
udp_unknown = ProtoField.int32("baichuan.udp_unknown", "udp_unknown", base.DEC)
udp_tid = ProtoField.int32("baichuan.udp_tid", "udp_tid", base.DEC)
udp_checksum = ProtoField.int32("baichuan.udp_checksum", "udp_checksum", base.DEC)
udp_packet_count = ProtoField.int32("baichuan.udp_packet_count", "udp_packet_count", base.DEC)
udp_last_ack_packet = ProtoField.int32("baichuan.udp_last_ack_packet", "udp_last_ack_packet", base.DEC)
udp_size = ProtoField.int32("baichuan.udp_size", "udp_size", base.DEC)
magic_bytes = ProtoField.int32("baichuan.magic", "magic", base.DEC)
message_id =  ProtoField.int32("baichuan.msg_id", "messageId", base.DEC)
message_len = ProtoField.int32("baichuan.msg_len", "messageLen", base.DEC)
xml_enc_offset = ProtoField.int32("baichuan.xml_encryption_offset", "xmlEncryptionOffset", base.DEC)
xml_enc_used = ProtoField.bool("baichuan.xml_encryption_used", "encrypted", base.NONE)
message_class = ProtoField.int32("baichuan.msg_class", "messageClass", base.DEC)
f_bin_offset = ProtoField.int32("baichuan.bin_offset", "binOffset", base.DEC)
username = ProtoField.string("baichuan.username", "username", base.ASCII)
password = ProtoField.string("baichuan.password", "password", base.ASCII)

bc_protocol.fields = {
  udp_message_id,
  udp_connection_id,
  udp_unknown,
  udp_tid,
  udp_checksum,
  udp_packet_count,
  udp_last_ack_packet,
  udp_size,
  magic_bytes,
  message_id,
  message_len,
  xml_enc_offset,
  xml_enc_used,
  message_class,
  f_bin_offset,
  username,
  password,
}

message_types = {
  [1]="login",
  [2]="logout",
  [3]="<Preview> (video)",
  [10]="Extension?",
  [58]="<AbilitySupport>",
  [78]="<VideoInput>",
  [79]="<Serial>",
  [80]="<VersionInfo>",
  [93]="ping",
  [114]="<Uid>",
  [115]="WifiSignal?",
  [146]="<StreamInfoList>",
  [151]="<AbilityInfo>",
  [199]="Support?",
  [230]="<cropSnap>",
}

message_classes = {
  [0x6514]="legacy",
  [0x6614]="modern",
  [0x6414]="modern",
  [0x0000]="modern",
}

header_lengths = {
  [0x6514]=20,
  [0x6614]=20,
  [0x6414]=24,
  [0x0000]=24,
}

function rshift(x, by)
  return math.floor(x / 2 ^ by)
end

function udp_decrypt(data, tid)
  local result = ByteArray.new()
  result:set_size(data:len())
  local key = {
    0x1f2d3c4b, 0x5a6c7f8d, 
    0x38172e4b, 0x8271635a,
    0x863f1a2b, 0xa5c6f7d8, 
    0x8371e1b4, 0x17f2d3a5
  }
 
  for i=1, 8 do
    key[i] = key[i] + tid
  end
  print(tid)

  local i = data:len() + 3
  if i < 0 then
    i = data:len() + 6
  end

  for x=0, rshift(i, 2) do
    local index = bit32.band(x, 7)
    local xor_key_word = key[index + 1]
    for b=0, 3 do
      byte_index = x * 4 + b
      local val = data:get_index(byte_index)
      local key_byte = bit32.extract(xor_key_word, b*8, 8)
      print("xor_key_word " .. xor_key_word .. " B " .. b .. " extracted_byte " .. key_byte)
      val = bit32.bxor(key_byte, val)
      result:set_index(byte_index, val)
      if byte_index >= data:len() - 1 then
        return result
      end
    end
  end
  return result
end

function xml_decrypt(data, offset)
  local key = "\031\045\060\075\090\105\120\255"
  local result = ByteArray.new()
  result:set_size(data:len())
  for i=0, data:len() - 1 do
    result:set_index(i, bit32.bxor(bit32.band(offset, 0xFF), bit32.bxor(data:get_index(i), key:byte(((i + offset) % 8) + 1))))
  end
  return result
end

function bc_protocol.dissector(buffer, pinfo, tree)
  length = buffer:len()
  if length == 0 then return end

  if buffer:len() < 20 then
    -- Need more bytes but we don't have a header to learn how many bytes
    pinfo.desegment_len = DESEGMENT_ONE_MORE_SEGMENT
    pinfo.desegment_offset = 0
    return
  end

  pinfo.cols.protocol = bc_protocol.name

  local udp_wrap_offset = 20

  local bc_subtree = tree:add(bc_protocol, buffer(), "Baichuan IP Camera Protocol")
  local udp_header = bc_subtree:add(bc_protocol, buffer(0, 20), "Baichuan UDP Message Header")

  udp_message_id_buffer = buffer(0, 4)
  udp_header:add_le(udp_message_id, udp_message_id_buffer)
  if (udp_message_id_buffer:le_uint() == 0x2a87cf3a) then
    udp_size_buffer = buffer(4, 4)
    udp_header:add_le(udp_size, udp_size_buffer)
    udp_header:add_le(udp_unknown, buffer(8, 4))
    udp_tid_buffer = buffer(12, 4)
    udp_header:add_le(udp_tid, udp_tid_buffer)
    udp_header:add_le(udp_checksum, buffer(16, 4))

    udp_body_buffer = buffer(20, udp_size_buffer:le_uint())
    local udp_body = bc_subtree:add(bc_protocol, udp_body_buffer, "Baichuan UDP Message Body")
    local body_bytes = udp_body_buffer:bytes()
    local decrypted = udp_decrypt(body_bytes, udp_tid_buffer:le_int())
    body_tvb = decrypted:tvb("Decrypted Message")
    -- Create a tree item that, when clicked, automatically shows the tab we just created
    udp_body:add(body_tvb(), "Decrypted Message")
  elseif (udp_message_id_buffer:le_uint() == 0x2a87cf20) then
    udp_header:add_le(udp_connection_id, buffer(4, 4))
    udp_header:add_le(udp_unknown, buffer(8, 4))

    udp_header:add_le(udp_unknown, buffer(12, 4))
    udp_header:add_le(udp_last_ack_packet, buffer(16, 4))
    udp_header:add_le(udp_unknown, buffer(20, 4))
    udp_header:add_le(udp_unknown, buffer(24, 4))
  else
    udp_header:add_le(udp_connection_id, buffer(4, 4))
    udp_header:add_le(udp_unknown, buffer(8, 4))

    udp_header:add_le(udp_packet_count, buffer(12, 4))
    udp_header:add_le(udp_size, buffer(16, 4))
  end

  local magic = buffer(0 + udp_wrap_offset, 4):le_uint()
  if magic ~= 0x0abcdef0 then
    -- Case 3, capture started in middle of packet,
    -- from https://wiki.wireshark.org/Lua/Dissectors#TCP_reassembly
    -- The camera always seems to emit a new TCP packet for a new message
    return 0
  end

  local msg_type = buffer(4 + udp_wrap_offset, 4):le_uint()
  local msg_type_str = message_types[msg_type] or "unknown"
  local msg_len = buffer(8 + udp_wrap_offset, 4):le_uint()
  local enc_offset = buffer(12 + udp_wrap_offset, 4):le_uint()
  local msg_cls = buffer(18 + udp_wrap_offset, 2):le_uint()
  local encrypted = (msg_cls == 0x6414 or buffer(16 + udp_wrap_offset, 1):le_uint() ~= 0)
  local class = message_classes[buffer(18 + udp_wrap_offset, 2):le_uint()]
  local header_len = header_lengths[buffer(18 + udp_wrap_offset, 2):le_uint()]

  -- if buffer:len() ~= msg_len + header_len then
  --   -- Case 1, need more bytes,
  --   -- from https://wiki.wireshark.org/Lua/Dissectors#TCP_reassembly
  --   pinfo.desegment_len = msg_len + header_len - buffer:len()
  --   pinfo.desegment_offset = 0
  --   return buffer:len()
  -- end

  -- bin_offset is either nil (no binary data) or nonzero
  -- TODO: bin_offset is actually stateful!
  local bin_offset = nil
  if header_len == 24 then
    bin_offset = buffer(20 + udp_wrap_offset, 4):le_uint()
    if bin_offset == 0 then bin_offset = nil end
  end

  local header = bc_subtree:add(bc_protocol, buffer(0 + udp_wrap_offset, header_len), "Baichuan Message Header, length: " .. header_len)

  pinfo.cols['info'] = msg_type_str .. ", type " .. msg_type .. ", " .. msg_len .. " bytes"

  header:add_le(magic_bytes, buffer(0 + udp_wrap_offset, 4))
  header:add_le(message_id,  buffer(4 + udp_wrap_offset, 4))
        :append_text(" (" .. msg_type_str .. ")")
  header:add_le(message_len, buffer(8 + udp_wrap_offset, 4))
  header:add_le(xml_enc_offset, buffer(12 + udp_wrap_offset, 4))
        :append_text(" (& 0xF == " .. bit32.band(enc_offset, 0xF) .. ")")
  header:add_le(xml_enc_used, buffer(16 + udp_wrap_offset, 1))
  header:add_le(message_class, buffer(18 + udp_wrap_offset, 2))
        :append_text(" (" .. class .. ")")
  header:add_le(f_bin_offset, buffer(20 + udp_wrap_offset, 4))

  if msg_len == 0 then
    return
  end

  local body = bc_subtree:add(bc_protocol, buffer(header_len + udp_wrap_offset, nil), "Baichuan Message Body, " .. class .. ", length: " .. msg_len .. ", encrypted: " .. tostring(encrypted))

  if class == "legacy" then
    if msg_type == 1 then
      body:add_le(username, buffer(header_len + udp_wrap_offset, 32))
      body:add_le(password, buffer(header_len + 32 + udp_wrap_offset, 32))
    end
  else
    local body_tvb = buffer(header_len + udp_wrap_offset, bin_offset):tvb()
    body:add(body_tvb(), "XML Payload")

    if encrypted then
      local ba = buffer(header_len + udp_wrap_offset, bin_offset):bytes()
      local decrypted = xml_decrypt(ba, enc_offset)
      body_tvb = decrypted:tvb("Decrypted XML")
      -- Create a tree item that, when clicked, automatically shows the tab we just created
      body:add(body_tvb(), "Decrypted XML")
    end
    Dissector.get("xml"):call(body_tvb, pinfo, body)

    if bin_offset ~= nil then
      local binary_tvb = buffer(header_len + bin_offset + udp_wrap_offset, nil):tvb()
      body:add(binary_tvb(), "Binary Payload")
      if msg_type == 0x03 then -- video
        Dissector.get("h265"):call(binary_tvb, pinfo, tree)
      end
    end
  end
end

-- DissectorTable.get("tcp.port"):add(9000, bc_protocol)
DissectorTable.get("udp.port"):add(29237, bc_protocol)
DissectorTable.get("udp.port"):add(39654, bc_protocol)
DissectorTable.get("udp.port"):add(28100, bc_protocol)
DissectorTable.get("udp.port"):add(13154, bc_protocol)
DissectorTable.get("udp.port"):add(2015, bc_protocol)