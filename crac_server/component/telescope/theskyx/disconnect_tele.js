/* Java Script */
/* Socket Start Packet */
var dRa = "{ra}"; 
var dDec = "{dec}";
var name = "park sync";
var Out;
/* Make a simpler name for output. */
var console = RunJavaScriptOutput;

/* Disconnect this scriptable object to the mount hardware and the mount hardware to TheSky if not connected already. */
sky6RASCOMTele.Disconnect();
sky6RASCOMTele.DisconnectTelescope();

Out;

/* Socket End Packet */
