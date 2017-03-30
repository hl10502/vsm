
function RenamePool(){
	//Check the field is should not null
	if($("#txtPoolName").val() == ""){
		showTip("error","The field is marked as '*' should not be empty");
		return  false;
	}
	var data = {
		"pool":{
			"pool_id":$("#pool_id").val(),
			"name":$("#new_name").val()
		}
	};

	var postData = JSON.stringify(data);
	token = $("input[name=csrfmiddlewaretoken]").val();
	$.ajax({
		type: "post",
		url: "/dashboard/vsm/poolsmanagement/rename_pool_action/",
		data: postData,
		dataType:"json",
		success: function(data){
				//alert(data.status)
				//console.log(data);
                if(data.status == "OK"){
                    window.location.href="/dashboard/vsm/poolsmanagement/";
                }
                else{
                    showTip("error",data.message);
                }
		},
		error: function (XMLHttpRequest, textStatus, errorThrown) {
				if(XMLHttpRequest.status == 500)
                	showTip("error","INTERNAL SERVER ERROR")
		},
		headers: {
			"X-CSRFToken": token
		},
		complete: function(){

		}
    });
}

$(document).ajaxStart(function(){
    //load the spin
    ShowSpin();
});