
!---------------------------------------------------------------------
!---------------------------------------------------------------------

subroutine adi

!---------------------------------------------------------------------
!---------------------------------------------------------------------

  call copy_faces

  call txinvr

  call x_solve

  call y_solve

  call z_solve

  call add

  return
end

