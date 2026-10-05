package com.jota.link.network

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

object WakeOnLan {

    suspend fun sendMagicPacket(
        macStr: String,
        broadcastIp: String = "255.255.255.255",
        port: Int = 9
    ): Boolean = withContext(Dispatchers.IO) {
        try {
            val cleanMac = macStr.replace(":", "").replace("-", "")
            if (cleanMac.length != 12) {
                return@withContext false
            }

            val macBytes = ByteArray(6)
            for (i in 0 until 6) {
                macBytes[i] = cleanMac.substring(i * 2, i * 2 + 2).toInt(16).toByte()
            }

            // Paquete magico: 6 veces 0xFF seguido de 16 repeticiones de la MAC (102 bytes)
            val packetData = ByteArray(6 + 16 * macBytes.size)
            for (i in 0 until 6) {
                packetData[i] = 0xFF.toByte()
            }
            for (i in 1..16) {
                System.arraycopy(macBytes, 0, packetData, i * 6, 6)
            }

            val address = InetAddress.getByName(broadcastIp)
            DatagramSocket().use { socket ->
                socket.broadcast = true
                val packet = DatagramPacket(packetData, packetData.size, address, port)
                socket.send(packet)
            }
            true
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }
}
