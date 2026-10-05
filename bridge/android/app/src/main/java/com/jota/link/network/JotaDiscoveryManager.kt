package com.jota.link.network

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Handler
import android.os.Looper
import android.util.Log

/**
 * Gestor de descubrimiento de red ZeroConf / mDNS nativo para Jota Bridge.
 * Utiliza android.net.nsd.NsdManager sin ninguna libreria externa.
 * Busca anuncios de tipo "_jota-bridge._tcp" emitidos por el PC Fedora.
 */
class JotaDiscoveryManager(
    private val context: Context,
    private val onServerFound: (host: String, port: Int, serviceName: String) -> Unit,
    private val onDiscoveryFinished: (foundCount: Int) -> Unit = {}
) {
    private val tag = "JotaDiscovery"
    private val serviceType = "_jota-bridge._tcp."
    private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as? NsdManager
    private val mainHandler = Handler(Looper.getMainLooper())

    private var isDiscovering = false
    private var foundServicesCount = 0

    private val discoveryListener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(regType: String) {
            Log.d(tag, "mDNS Discovery iniciado para tipo: $regType")
            isDiscovering = true
            foundServicesCount = 0
        }

        override fun onServiceFound(serviceInfo: NsdServiceInfo) {
            Log.d(tag, "Servicio mDNS encontrado: ${serviceInfo.serviceName} (${serviceInfo.serviceType})")
            if (serviceInfo.serviceType.contains("_jota-bridge")) {
                try {
                    nsdManager?.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                        override fun onServiceResolved(resolvedInfo: NsdServiceInfo) {
                            val host = resolvedInfo.host?.hostAddress
                            val port = resolvedInfo.port
                            val name = resolvedInfo.serviceName ?: "Jota Bridge"

                            Log.i(tag, "Jota Bridge resuelto con exito: http://$host:$port ($name)")
                            if (!host.isNullOrBlank() && port > 0) {
                                foundServicesCount++
                                mainHandler.post {
                                    onServerFound(host, port, name)
                                }
                            }
                        }

                        override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                            Log.w(tag, "Fallo al resolver servicio ${serviceInfo.serviceName}: error $errorCode")
                        }
                    })
                } catch (e: Exception) {
                    Log.e(tag, "Excepcion al solicitar resolucion de servicio: ${e.message}")
                }
            }
        }

        override fun onServiceLost(serviceInfo: NsdServiceInfo) {
            Log.d(tag, "Servicio mDNS perdido: ${serviceInfo.serviceName}")
        }

        override fun onDiscoveryStopped(serviceType: String) {
            Log.d(tag, "mDNS Discovery detenido.")
            isDiscovering = false
            mainHandler.post {
                onDiscoveryFinished(foundServicesCount)
            }
        }

        override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e(tag, "Fallo al iniciar discovery ($serviceType): error $errorCode")
            isDiscovering = false
            nsdManager?.stopServiceDiscovery(this)
            mainHandler.post {
                onDiscoveryFinished(0)
            }
        }

        override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
            Log.e(tag, "Fallo al detener discovery: error $errorCode")
            isDiscovering = false
        }
    }

    /**
     * Inicia la busqueda de instancias de Jota Bridge en la red local.
     * Se detiene automaticamente tras [timeoutMs] milisegundos.
     */
    fun startDiscovery(timeoutMs: Long = 6000L) {
        if (isDiscovering || nsdManager == null) return
        try {
            nsdManager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discoveryListener)
            // Detener automaticamente tras timeout para ahorrar bateria
            mainHandler.postDelayed({
                stopDiscovery()
            }, timeoutMs)
        } catch (e: Exception) {
            Log.e(tag, "No se pudo iniciar el descubrimiento NsdManager: ${e.message}")
            isDiscovering = false
            onDiscoveryFinished(0)
        }
    }

    /**
     * Detiene la busqueda activa de servicios.
     */
    fun stopDiscovery() {
        if (!isDiscovering || nsdManager == null) return
        try {
            nsdManager.stopServiceDiscovery(discoveryListener)
        } catch (e: Exception) {
            Log.d(tag, "Error deteniendo discovery (puede ya estar parado): ${e.message}")
        } finally {
            isDiscovering = false
        }
    }
}
