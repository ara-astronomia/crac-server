/* Java Script */
/* Socket Start Packet */
var dRa = "{ra}"; 
var dDec = "{dec}";
var name = "park sync";
var Out;
/* Make a simpler name for output. */
var console = RunJavaScriptOutput;

/* Connect this scriptable object to the mount hardware and the mount hardware to TheSky if not connected already. */
sky6RASCOMTele.Connect();

if (sky6RASCOMTele.IsConnected==0)//Connect failed for some reason
{{
    console.writeLine("Mount not connected.");
}}
else
{{
    /* Slew synchronously and simply block until the slew is complete. */
    sky6RASCOMTele.Sync(dRa, dDec, name);
    Out;
}}

/* Socket End Packet */
